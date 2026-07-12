"""Compact historical replay simulation trading workbench."""
from __future__ import annotations

from datetime import date, timedelta
import logging
import pandas as pd
import streamlit as st

from components.candlestick_chart import create_candlestick_figure
from components.charts import make_line_chart, make_macd_chart, make_volume_chart
from components.simulation_charts import equity_and_drawdown_chart
from database.db import DatabaseError
from services.analysis_cache import cached_prepare_chart_data
from services.chart_data import ChartDataError, filter_data_by_period
from services.market_data import MarketDataError, YahooMarketDataProvider
from simulation.fee_config import SimulationFeeConfig
from simulation.market_clock import HistoricalMarketClock, MarketClockError, history_request_start
from simulation.models import SimulationOrder
from simulation.repository import SimulationRepository
from simulation.simulation_engine import SimulationEngine, SimulationValidationError
from utils.formatters import currency_compact, currency_full
from utils.logging_config import configure_logging
from utils.i18n import current_language, language_selector, tr

try:
    from utils.i18n import interval_code, interval_labels
except ImportError:  # Compatibility with an older module retained by Streamlit hot reload.
    def interval_labels() -> list[str]:
        return ["Daily", "Weekly", "Monthly"] if current_language() == "en" else ["日K", "周K", "月K"]

    def interval_code(label: str) -> str:
        return {"Daily": "日K", "Weekly": "周K", "Monthly": "月K"}.get(label, label)
from utils.validators import validate_stock_code

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="模拟交易工作台 | TradeBot", page_icon="🧪", layout="wide")
repository = SimulationRepository()
engine = SimulationEngine(repository)

st.markdown("""<style>
div[data-testid="stMetric"]{padding:.35rem .55rem;border:1px solid rgba(120,130,150,.2);border-radius:.5rem}
div[data-testid="stMetricValue"]{font-size:1.15rem} div[data-testid="stMetricLabel"]{font-size:.78rem}
.block-container{padding-top:1rem;padding-bottom:2rem}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner=False)
def load_history(code: str, start: date) -> tuple[str, pd.DataFrame]:
    history = YahooMarketDataProvider().get_stock_history(code, history_request_start(start), date.today())
    return history.name, history.prices


def create_account_panel() -> None:
    with st.expander(tr("新建模拟账户","New Simulation Account"), expanded=not repository.list_accounts()):
        with st.form("create_simulation_account"):
            name = st.text_input(tr("账户名称","Account Name"), placeholder=tr("例如：2024 年历史练习","Example: 2024 Replay Practice"))
            initial_cash = st.number_input(tr("初始资金（元）","Initial Cash (CNY)"), min_value=1_000.0, value=100_000.0, step=10_000.0)
            requested_start = st.date_input(tr("历史开始日期","Historical Start Date"), value=date.today()-timedelta(days=365), max_value=date.today())
            commission_rate = st.number_input(tr("佣金率","Commission Rate"), min_value=0.0, value=0.0003, format="%.5f")
            minimum_commission = st.number_input(tr("最低佣金","Minimum Commission"), min_value=0.0, value=5.0)
            sell_tax_rate = st.number_input(tr("卖出税率","Sell Tax Rate"), min_value=0.0, value=0.0005, format="%.5f")
            slippage_bps = st.number_input(tr("滑点（基点）","Slippage (bps)"), min_value=0.0, value=2.0)
            submitted = st.form_submit_button(tr("创建账户","Create Account"), type="primary", width="stretch")
        if submitted:
            _, benchmark = load_history("000001", requested_start)
            start = HistoricalMarketClock(benchmark).normalize_start_date(requested_start)
            config = SimulationFeeConfig(commission_rate, minimum_commission, sell_tax_rate, slippage_bps)
            account = repository.create_account(name, initial_cash, start, config)
            engine.create_initial_snapshot(account.id)
            st.session_state["simulation_account_id"] = account.id
            st.rerun()


def current_snapshot(account_id: int):
    snapshots = repository.list_snapshots(account_id)
    return snapshots[-1] if snapshots else engine.create_initial_snapshot(account_id)


def advance_account(account) -> None:
    _, benchmark = load_history("000001", account.start_date)
    codes = {item.stock_code for item in engine.positions(account.id, account.current_date)}
    codes.update(item.stock_code for item in repository.list_orders(account.id, "PENDING"))
    market_data = {code: load_history(code, account.start_date)[1] for code in codes}
    engine.advance_to_next_day(account.id, HistoricalMarketClock(benchmark), market_data)


def position_rows(account) -> list[dict[str, object]]:
    rows = []
    for position in engine.positions(account.id, account.current_date):
        _, history = load_history(position.stock_code, account.start_date)
        allowed = HistoricalMarketClock(history).visible_bars(account.current_date)
        close = float(allowed.iloc[-1]["close"])
        rows.append({"代码":position.stock_code,"名称":position.stock_name,"总数量":position.quantity,
                     "可卖数量":position.sellable_quantity,"平均成本":round(position.average_cost,4),
                     "当前收盘":round(close,4),"持仓市值":round(position.quantity*close,2),
                     "浮动盈亏":round(position.quantity*(close-position.average_cost),2)})
    return rows


@st.fragment
def render_market_workspace(allowed_daily: pd.DataFrame, account, code: str, stock_name: str) -> None:
    controls = st.columns([2.2,1.2,2.5])
    period = controls[0].segmented_control(tr("周期","Range"), ["1M","3M","6M","1Y","3Y","5Y","MAX"],
                                            default="3M", key="simulation_chart_period") or "3M"
    interval_context = (period,current_language())
    if st.session_state.get("_simulation_interval_context") != interval_context:
        default_code = "周K" if period in ("3Y","5Y","MAX") else "日K"
        st.session_state["simulation_chart_interval_display"] = {"日K":tr("日K","Daily"),"周K":tr("周K","Weekly"),"月K":tr("月K","Monthly")}[default_code]
        st.session_state["_simulation_interval_context"] = interval_context
    interval_display = controls[1].segmented_control(tr("粒度","Interval"), interval_labels(),
                                              key="simulation_chart_interval_display") or interval_labels()[0]
    interval = interval_code(interval_display)
    st.session_state.setdefault("simulation_overlays", ["MA5","MA10","MA20","MA60"])
    overlays = controls[2].multiselect(tr("主图叠加","Overlays"), ["MA5","MA10","MA20","MA60","BOLL"],
                                       key="simulation_overlays")
    analyzed = cached_prepare_chart_data(allowed_daily, interval)
    chart_data = filter_data_by_period(analyzed, period, pd.Timestamp(account.current_date))
    ma_windows = [int(item.removeprefix("MA")) for item in overlays if item.startswith("MA")]
    main = create_candlestick_figure(chart_data, period, f"{stock_name}（{code}）｜截止 {account.current_date}",
        interval=interval_display, show_ma=ma_windows, show_boll="BOLL" in overlays,
        show_volume_ma=False, include_volume_panel=False, height=460)
    st.plotly_chart(main, width="stretch", config={"scrollZoom":True,"displaylogo":False})

    volume_label = tr("成交量","Volume")
    if st.session_state.get("_simulation_secondary_language") != current_language():
        if st.session_state.get("simulation_secondary_indicator") in ("成交量","Volume",None):
            st.session_state["simulation_secondary_indicator"] = volume_label
        st.session_state["_simulation_secondary_language"] = current_language()
    secondary = st.segmented_control(tr("副指标","Secondary Indicator"), [volume_label,"MACD","RSI","KDJ"], default=volume_label,
                                      key="simulation_secondary_indicator") or volume_label
    if secondary == volume_label:
        figure = make_volume_chart(chart_data)
    elif secondary == "MACD":
        figure = make_macd_chart(chart_data)
    elif secondary == "RSI":
        figure = make_line_chart(chart_data,["rsi14"],["RSI14"],"RSI（Wilder 14）",[30,70])
    else:
        figure = make_line_chart(chart_data,["k","d","j"],["K","D","J"],"KDJ（9,3,3）",[20,80])
    figure.update_layout(height=260, margin={"l":20,"r":20,"t":45,"b":20})
    st.plotly_chart(figure, width="stretch", config={"displaylogo":False})


def render_order_panel(account, code: str, stock_name: str, latest_close: float, stock_position) -> None:
    st.markdown(tr("#### 当前股票持仓", "#### Current Ticker Position"))
    quantity = stock_position.quantity if stock_position else 0
    sellable = stock_position.sellable_quantity if stock_position else 0
    average_cost = stock_position.average_cost if stock_position else 0.0
    unrealized = quantity*(latest_close-average_cost) if stock_position else 0.0
    row = st.columns(2); row[0].metric(tr("总数量","Total Qty"),f"{quantity:,}"); row[1].metric(tr("可卖数量","Sellable"),f"{sellable:,}")
    row = st.columns(2); row[0].metric(tr("平均成本","Avg Cost"),f"¥{average_cost:.2f}"); row[1].metric(tr("浮动盈亏","Unrealized P&L"),currency_compact(unrealized),help=currency_full(unrealized))
    st.markdown(tr("#### 模拟下单", "#### Simulated Order"))
    st.session_state.setdefault("simulation_trade_side","BUY")
    st.session_state.setdefault("simulation_order_quantity",100)
    reference_quantity = int(st.session_state["simulation_order_quantity"])
    st.caption(f"{tr('收盘参考','Close reference')} ¥{latest_close:.2f}｜{tr('参考金额','Estimated value')} {currency_full(latest_close*reference_quantity)}")
    with st.form("simulation_order_form"):
        side = st.segmented_control(tr("方向","Side"),["BUY","SELL"],key="simulation_trade_side") or "BUY"
        order_quantity = st.number_input(tr("数量（股）","Quantity (shares)"),min_value=1,step=100,key="simulation_order_quantity")
        with st.expander(tr("交易计划（可选）","Trade Plan (optional)")):
            reason = st.text_area(tr("交易理由","Trade rationale"),key="simulation_trade_reason")
            holding = st.text_input(tr("计划持有周期","Planned holding period"),key="simulation_holding_period")
            stop_loss = st.text_input(tr("止损条件","Stop-loss condition"),help=tr("仅记录，不自动触发","Recorded only; not triggered automatically"),key="simulation_stop_loss")
            target = st.text_input(tr("目标条件","Target condition"),help=tr("仅记录，不自动触发","Recorded only; not triggered automatically"),key="simulation_target")
            confidence = st.slider(tr("信心等级","Confidence"),1,5,3,key="simulation_confidence")
        submitted = st.form_submit_button(tr("提交次日开盘订单","Submit for next-day open"),type="primary",width="stretch")
    if submitted:
        created = engine.submit_order(SimulationOrder(account.id,code,stock_name,side,int(order_quantity),
            account.current_date,reason=reason,planned_holding_period=holding,stop_loss_condition=stop_loss,
            target_condition=target,confidence_level=confidence))
        st.success(f"订单 #{created.id} 已进入 PENDING")
        st.rerun()


st.title(tr("模拟交易工作台", "Simulation Trading Workbench"))
try:
    with st.sidebar:
        st.markdown(tr("### 模拟盘","### Simulation")); language_selector(); st.caption(tr("与真实持仓完全隔离，不连接券商。","Fully isolated from real positions; no broker connection."))
        create_account_panel()
    accounts = repository.list_accounts()
    if not accounts:
        st.info(tr("请在侧栏创建模拟账户。","Create a simulation account in the sidebar.")); st.stop()
    account_ids = [item.id for item in accounts]
    if st.session_state.get("simulation_account_id") not in account_ids:
        st.session_state["simulation_account_id"] = account_ids[0]
    labels = {item.id:f"{item.name}（#{item.id}）" for item in accounts}

    with st.container(border=True):
        controls = st.columns([2.2,1.25,.9,1.05])
        selected_id = controls[0].selectbox(tr("模拟账户","Simulation Account"),account_ids,format_func=labels.get,
                                            key="simulation_account_id",label_visibility="collapsed")
        account = repository.get_account(selected_id); snapshot = current_snapshot(account.id)
        st.session_state["simulation_current_date"] = account.current_date.isoformat()
        controls[1].markdown(f"**{tr('模拟日期','Simulation Date')}**<br>{account.current_date}",unsafe_allow_html=True)
        controls[2].button(tr("← 上一日","← Previous"),disabled=True,help=tr("已有成交和快照不可逆，当前规则不支持回退","Filled orders and snapshots are irreversible"),width="stretch")
        if controls[3].button(tr("下一交易日 →","Next Day →"),type="primary",width="stretch"):
            advance_account(account); st.rerun()
        metrics = st.columns(4)
        metrics[0].metric(tr("总资产","Total Assets"),currency_compact(snapshot.total_assets),help=currency_full(snapshot.total_assets))
        metrics[1].metric(tr("累计收益率","Cumulative Return"),f"{snapshot.cumulative_return:.2%}")
        metrics[2].metric(tr("当前回撤","Current Drawdown"),f"{snapshot.current_drawdown:.2%}")
        metrics[3].metric(tr("可用现金","Available Cash"),currency_compact(snapshot.cash_balance),help=currency_full(snapshot.cash_balance))

    left,right = st.columns([3,1],gap="medium")
    with left:
        code_input = st.text_input(tr("股票代码","Ticker"),value=st.session_state.get("sim_code","000001"),max_chars=6,
                                   key="simulation_stock_input",placeholder=tr("六位A股代码","Six-digit A-share code"))
        code = validate_stock_code(code_input); st.session_state["sim_code"] = code
        stock_name,complete_history = load_history(code,account.start_date)
        allowed_daily = HistoricalMarketClock(complete_history).visible_bars(account.current_date)
        if allowed_daily.empty: raise MarketClockError("该股票在当前模拟日期以前没有行情")
        latest = allowed_daily.iloc[-1]; latest_close = float(latest["close"])
        change_pct = float(latest.get("change_pct",0) or 0)
        st.markdown(f"**{stock_name}（{code}）**　收盘 **¥{latest_close:.2f}**　涨跌幅 **{change_pct:.2f}%**　数据日 **{latest['date']}**")
        render_market_workspace(allowed_daily,account,code,stock_name)
    positions = engine.positions(account.id,account.current_date)
    stock_position = next((item for item in positions if item.stock_code==code),None)
    with right:
        with st.container(border=True): render_order_panel(account,code,stock_name,latest_close,stock_position)

    st.divider()
    bottom_map = {
        tr("当前持仓","Positions"):"positions", tr("待执行订单","Pending Orders"):"pending",
        tr("成交记录","Order History"):"history", tr("账户净值","Equity"):"equity",
        tr("交易复盘","Trade Review"):"review",
    }
    if st.session_state.get("_simulation_bottom_language") != current_language():
        old = st.session_state.get("simulation_bottom_view")
        semantic = {"当前持仓":"positions","Positions":"positions","待执行订单":"pending","Pending Orders":"pending",
                    "成交记录":"history","Order History":"history","账户净值":"equity","Equity":"equity",
                    "交易复盘":"review","Trade Review":"review"}.get(old,"positions")
        st.session_state["simulation_bottom_view"] = next(label for label,value in bottom_map.items() if value==semantic)
        st.session_state["_simulation_bottom_language"] = current_language()
    bottom_label = st.segmented_control(tr("账户工作区","Account Workspace"),list(bottom_map),
                                       key="simulation_bottom_view") or next(iter(bottom_map))
    bottom_view = bottom_map[bottom_label]
    orders = repository.list_orders(account.id)
    if bottom_view == "positions":
        rows = position_rows(account)
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True) if rows else st.info("当前没有模拟持仓。")
    elif bottom_view == "pending":
        pending = [item for item in orders if item.status=="PENDING"]
        if pending:
            st.dataframe(pd.DataFrame([{"ID":i.id,"提交日":i.submitted_date,"代码":i.stock_code,"方向":i.side,"数量":i.quantity,"理由":i.reason} for i in pending]),width="stretch",hide_index=True)
            cancel_id = st.selectbox("取消订单",[i.id for i in pending],format_func=lambda value:f"订单 #{value}")
            if st.button("取消选中订单"): engine.cancel_order(account.id,int(cancel_id)); st.rerun()
        else: st.info("没有待执行订单。")
    elif bottom_view == "history":
        finished = [i for i in orders if i.status in ("FILLED","REJECTED","CANCELLED")]
        rows = [{"ID":i.id,"提交日":i.submitted_date,"执行日":i.execution_date,"代码":i.stock_code,"方向":i.side,"数量":i.quantity,"状态":i.status,"成交价":i.fill_price,"佣金":i.commission,"税费":i.tax,"拒绝原因":i.rejection_reason} for i in finished]
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True) if rows else st.info("暂无已结束订单。")
    elif bottom_view == "equity":
        st.plotly_chart(equity_and_drawdown_chart(repository.list_snapshots(account.id)),width="stretch")
    else:
        rows = [{"ID":i.id,"代码":i.stock_code,"方向":i.side,"交易理由":i.reason,"持有计划":i.planned_holding_period,"止损条件":i.stop_loss_condition,"目标条件":i.target_condition,"信心":i.confidence_level,"结果":i.status} for i in orders]
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True) if rows else st.info("暂无交易复盘记录。")
except (ValueError,DatabaseError,MarketDataError,MarketClockError,SimulationValidationError,ChartDataError) as exc:
    st.error(str(exc))
except Exception:
    LOGGER.exception("Unexpected simulation workbench error"); st.error("模拟盘页面处理失败，详细错误已写入日志。")
