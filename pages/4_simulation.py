"""Independent historical daily replay simulation page."""

from __future__ import annotations

from datetime import date, timedelta
import logging

import pandas as pd
import streamlit as st

from components.candlestick_chart import create_candlestick_figure
from components.charts import make_boll_chart, make_line_chart, make_macd_chart
from components.indicator_cards import render_status_cards
from components.simulation_charts import equity_and_drawdown_chart
from components.metric_cards import render_metric_grid
from database.db import DatabaseError
from services.market_data import MarketDataError, YahooMarketDataProvider
from services.indicators import IndicatorStatus, latest_statuses
from services.analysis_cache import cached_prepare_chart_data
from services.chart_data import ChartDataError, filter_data_by_period
from simulation.fee_config import SimulationFeeConfig
from simulation.market_clock import HistoricalMarketClock, MarketClockError, history_request_start
from simulation.models import SimulationOrder
from simulation.repository import SimulationRepository
from simulation.simulation_engine import SimulationEngine, SimulationValidationError
from utils.logging_config import configure_logging
from utils.formatters import currency_compact, currency_full
from utils.validators import validate_stock_code

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="模拟盘 | TradeBot", page_icon="🧪", layout="wide")
repository = SimulationRepository()
engine = SimulationEngine(repository)


@st.cache_data(ttl=1800, show_spinner=False)
def load_history(code: str, start: date) -> tuple[str, pd.DataFrame]:
    """Load history internally; callers must filter through HistoricalMarketClock before display."""
    history = YahooMarketDataProvider().get_stock_history(code, history_request_start(start), date.today())
    return history.name, history.prices


def create_account_panel() -> None:
    with st.expander("创建模拟账户", expanded=not repository.list_accounts()):
        with st.form("create_simulation_account"):
            name = st.text_input("账户名称", placeholder="例如：2024 年历史练习")
            initial_cash = st.number_input("初始资金（元）", min_value=1_000.0, value=100_000.0, step=10_000.0)
            requested_start = st.date_input("历史开始日期", value=date.today() - timedelta(days=365), max_value=date.today())
            columns = st.columns(4)
            commission_rate = columns[0].number_input("佣金率", min_value=0.0, value=0.0003, format="%.5f")
            minimum_commission = columns[1].number_input("最低佣金（元）", min_value=0.0, value=5.0)
            sell_tax_rate = columns[2].number_input("卖出税率", min_value=0.0, value=0.0005, format="%.5f")
            slippage_bps = columns[3].number_input("滑点（基点）", min_value=0.0, value=2.0)
            submitted = st.form_submit_button("创建账户", type="primary")
        if submitted:
            _, benchmark = load_history("000001", requested_start)
            start = HistoricalMarketClock(benchmark).normalize_start_date(requested_start)
            config = SimulationFeeConfig(commission_rate, minimum_commission, sell_tax_rate, slippage_bps)
            account = repository.create_account(name, initial_cash, start, config)
            engine.create_initial_snapshot(account.id)
            st.success(f"模拟账户已创建，首个模拟交易日：{start}")
            st.rerun()


def current_snapshot(account_id: int):
    snapshots = repository.list_snapshots(account_id)
    return snapshots[-1] if snapshots else engine.create_initial_snapshot(account_id)


def number(value: float, digits: int = 2) -> str:
    """Format warm-up indicator values without exposing NaN as a fake signal."""
    return "-" if pd.isna(value) else f"{value:.{digits}f}"


st.title("历史日线回放模拟盘")
st.warning("模拟盘与真实持仓完全隔离；不连接券商、不使用分钟行情、不执行真实交易。")

try:
    create_account_panel()
    accounts = repository.list_accounts()
    if not accounts:
        st.info("请先创建一个模拟账户。")
        st.stop()

    labels = {account.id: f"{account.name}（#{account.id}）" for account in accounts}
    selected_id = st.selectbox("选择模拟账户", list(labels), format_func=labels.get)
    account = repository.get_account(selected_id)
    snapshot = current_snapshot(account.id)

    st.subheader(f"{account.name}｜当前模拟日期：{account.current_date}")
    metrics = [
        ("可用现金", snapshot.cash_balance, "money"), ("持仓市值", snapshot.market_value, "money"),
        ("总资产", snapshot.total_assets, "money"), ("浮动盈亏", snapshot.unrealized_pnl, "money"),
        ("已实现盈亏", snapshot.realized_pnl, "money"), ("累计收益率", snapshot.cumulative_return, "pct"),
        ("每日收益率", snapshot.daily_return, "pct"), ("当前回撤", snapshot.current_drawdown, "pct"),
        ("最大回撤", snapshot.max_drawdown, "pct"),
    ]
    display_metrics = []
    for label, value, kind in metrics:
        if kind == "money":
            display_metrics.append((label, currency_compact(value), f"精确金额：{currency_full(value)}"))
        else:
            display_metrics.append((label, f"{value:.2%}", f"精确值：{value:.6%}"))
    render_metric_grid(display_metrics, columns_per_row=5)

    code = validate_stock_code(st.text_input("回放股票代码（仅六位 A 股）", value=st.session_state.get("sim_code", "000001")))
    st.session_state["sim_code"] = code
    stock_name, full_history = load_history(code, account.start_date)
    stock_clock = HistoricalMarketClock(full_history)
    visible = stock_clock.visible_bars(account.current_date)
    if visible.empty:
        st.info("该股票在当前模拟日期以前没有行情。")
    else:
        latest = visible.iloc[-1]
        st.caption(
            f"当前可见最后日线：{latest['date']}｜收盘 ¥{latest['close']:.2f}｜"
            "下一个交易日开盘价在推进前不会读取或显示。"
        )
        st.caption(
            f"技术图表从 Yahoo 可提供的最早日线开始（当前最早：{visible.iloc[0]['date']}），"
            f"并截止当前模拟日；交易净值仍从 {account.start_date} 开始计算。"
        )
        period = st.segmented_control(
            "K线显示周期", options=["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"],
            default="3M", key="simulation_chart_period",
        ) or "3M"
        last_period = st.session_state.get("_simulation_last_chart_period")
        if last_period != period:
            st.session_state["simulation_chart_interval"] = "周K" if period in ("3Y", "5Y", "MAX") else "日K"
            st.session_state["_simulation_last_chart_period"] = period
        interval = st.segmented_control(
            "K线粒度", options=["日K", "周K", "月K"], key="simulation_chart_interval",
        ) or "日K"
        # Critical ordering: future rows are removed above, then the complete
        # allowed history is aggregated and analyzed before display slicing.
        replay_data = cached_prepare_chart_data(visible, interval)
        statuses = latest_statuses(replay_data)
        render_status_cards([statuses[key] for key in ("trend", "macd", "rsi")])
        chart_data = filter_data_by_period(replay_data, period, pd.Timestamp(account.current_date))
        st.plotly_chart(
            create_candlestick_figure(
                chart_data,
                period,
                f"{stock_name}（{code}）历史回放｜截止 {account.current_date}｜K线与成交量",
                interval=interval,
            ),
            width="stretch", config={"scrollZoom": True, "displaylogo": False},
        )

        st.subheader("回放技术指标")
        st.caption("以下指标只使用当前模拟日期及以前的日线计算，不包含任何未来行情。")
        selected_indicator = st.segmented_control(
            "指标视图", options=["MACD", "RSI", "KDJ", "BOLL", "波动率"],
            default="MACD", key="simulation_indicator_view",
        ) or "MACD"
        indicator_row = replay_data.iloc[-1]
        if selected_indicator == "MACD":
            render_status_cards([statuses["macd"], statuses["volume"]])
            st.metric(
                "最新 DIF / DEA / 柱体",
                f"{number(indicator_row['dif'], 3)} / {number(indicator_row['dea'], 3)} / "
                f"{number(indicator_row['macd_hist'], 3)}",
            )
            st.plotly_chart(make_macd_chart(chart_data), width="stretch")
        elif selected_indicator == "RSI":
            render_status_cards([statuses["rsi"]])
            st.metric("最新 RSI14", number(indicator_row["rsi14"]))
            st.plotly_chart(
                make_line_chart(chart_data, ["rsi14"], ["RSI14"], "RSI（Wilder 14）", [30, 70]),
                width="stretch",
            )
        elif selected_indicator == "KDJ":
            kdj_values = indicator_row[["k", "d", "j"]]
            if kdj_values.isna().all():
                render_status_cards([])
            else:
                render_status_cards([IndicatorStatus(
                    "KDJ", "客观数值",
                    f"K {number(indicator_row['k'])}｜D {number(indicator_row['d'])}｜J {number(indicator_row['j'])}",
                )])
            st.metric(
                "最新 K / D / J",
                f"{number(indicator_row['k'])} / {number(indicator_row['d'])} / {number(indicator_row['j'])}",
            )
            st.plotly_chart(
                make_line_chart(chart_data, ["k", "d", "j"], ["K", "D", "J"], "KDJ（9, 3, 3）", [20, 80]),
                width="stretch",
            )
        elif selected_indicator == "BOLL":
            render_status_cards([statuses["boll"]])
            st.metric(
                "最新上轨 / 中轨 / 下轨",
                f"{number(indicator_row['boll_upper'])} / {number(indicator_row['boll_mid'])} / "
                f"{number(indicator_row['boll_lower'])}",
            )
            st.plotly_chart(make_boll_chart(chart_data), width="stretch")
        else:
            render_status_cards([statuses["volatility"]])
            volatility = indicator_row["volatility20"]
            st.metric("最新 20 日年化波动率", "-" if pd.isna(volatility) else f"{volatility:.2%}")
            st.plotly_chart(
                make_line_chart(
                    chart_data, ["volatility20"], ["20日年化波动率"], "20 日历史波动率"
                ),
                width="stretch",
            )

    order_tab, pending_tab, positions_tab, history_tab = st.tabs(["提交订单", "待处理订单", "模拟持仓", "订单与净值"])
    with order_tab:
        with st.form("simulation_order"):
            side = st.selectbox("方向", ["BUY", "SELL"])
            quantity = st.number_input("数量（股）", min_value=1, value=100, step=100)
            reason = st.text_area("交易理由")
            holding = st.text_input("计划持有周期", placeholder="例如：20 个交易日")
            stop_loss = st.text_input("止损条件", placeholder="仅记录，不自动触发")
            target = st.text_input("目标条件", placeholder="仅记录，不自动触发")
            confidence = st.slider("信心等级", 1, 5, 3)
            if st.form_submit_button("提交次日开盘订单", type="primary"):
                created = engine.submit_order(SimulationOrder(
                    account.id, code, stock_name, side, int(quantity), account.current_date,
                    reason=reason, planned_holding_period=holding, stop_loss_condition=stop_loss,
                    target_condition=target, confidence_level=confidence,
                ))
                st.success(f"订单 #{created.id} 已进入 PENDING，将在下一交易日开盘尝试执行。")
                st.rerun()

    with pending_tab:
        pending = repository.list_orders(account.id, "PENDING")
        if pending:
            st.dataframe(pd.DataFrame([{
                "ID": item.id, "提交日": item.submitted_date, "代码": item.stock_code,
                "方向": item.side, "数量": item.quantity, "理由": item.reason,
            } for item in pending]), width="stretch", hide_index=True)
            cancel_id = st.selectbox("取消订单 ID", [item.id for item in pending])
            if st.button("取消待处理订单"):
                engine.cancel_order(account.id, int(cancel_id))
                st.success("订单已取消。")
                st.rerun()
        else:
            st.info("没有待处理订单。")

    with positions_tab:
        positions = engine.positions(account.id, account.current_date)
        if positions:
            rows = []
            for position in positions:
                _, position_history = load_history(position.stock_code, account.start_date)
                position_visible = HistoricalMarketClock(position_history).visible_bars(account.current_date)
                close = float(position_visible.iloc[-1]["close"])
                rows.append({
                    "代码": position.stock_code, "名称": position.stock_name,
                    "持仓数量": position.quantity, "可卖数量": position.sellable_quantity,
                    "平均成本": round(position.average_cost, 4), "当前收盘": round(close, 4),
                    "持仓市值": round(position.quantity * close, 2),
                    "浮动盈亏": round(position.quantity * (close - position.average_cost), 2),
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("当前没有模拟持仓。")

    with history_tab:
        orders = repository.list_orders(account.id)
        if orders:
            st.dataframe(pd.DataFrame([{
                "ID": item.id, "提交日": item.submitted_date, "执行日": item.execution_date,
                "代码": item.stock_code, "方向": item.side, "数量": item.quantity,
                "状态": item.status, "成交价": item.fill_price, "佣金": item.commission,
                "税费": item.tax, "拒绝原因": item.rejection_reason,
                "交易理由": item.reason, "持有计划": item.planned_holding_period,
                "止损条件": item.stop_loss_condition, "目标条件": item.target_condition,
                "信心": item.confidence_level,
            } for item in orders]), width="stretch", hide_index=True)
        snapshots = repository.list_snapshots(account.id)
        st.plotly_chart(equity_and_drawdown_chart(snapshots), width="stretch")

    st.divider()
    st.caption("推进后将执行 PENDING 订单并保存收盘快照；该操作不可回退。")
    if st.button("进入下一交易日", type="primary"):
        _, benchmark = load_history("000001", account.start_date)
        codes = {item.stock_code for item in engine.positions(account.id, account.current_date)}
        codes.update(item.stock_code for item in repository.list_orders(account.id, "PENDING"))
        market_data = {item: load_history(item, account.start_date)[1] for item in codes}
        next_snapshot = engine.advance_to_next_day(account.id, HistoricalMarketClock(benchmark), market_data)
        st.success(f"已进入 {next_snapshot.snapshot_date}，待处理订单已完成撮合。")
        st.rerun()
except (ValueError, DatabaseError, MarketDataError, MarketClockError, SimulationValidationError, ChartDataError) as exc:
    st.error(str(exc))
except Exception:
    LOGGER.exception("Unexpected simulation page error")
    st.error("模拟盘页面处理失败，详细错误已写入日志。")
