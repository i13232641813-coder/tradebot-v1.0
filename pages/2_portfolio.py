"""Portfolio dashboard with CNY base-currency valuation."""

from datetime import datetime
import logging

import pandas as pd
import streamlit as st

from components.portfolio_charts import allocation_chart, market_value_chart, pnl_amount_chart, pnl_percent_chart
from components.metric_cards import render_metric_grid
from database.db import DatabaseError, TransactionRepository
from services.market_data import MarketDataError, YahooMarketDataProvider, default_history_range
from services.portfolio_service import PortfolioValidationError, calculate_positions, summarize_portfolio, value_positions
from utils.formatters import currency_compact, currency_full, percent, price
from utils.logging_config import configure_logging

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="我的持仓 | TradeBot", page_icon="💼", layout="wide")
repository = TransactionRepository()


@st.cache_data(ttl=60, show_spinner=False)
def latest_price(code: str) -> tuple[float, str]:
    """Prefer the latest minute quote and fall back to a dated daily close."""
    provider = YahooMarketDataProvider()
    try:
        quote = provider.get_latest_quote(code)
        return quote.price, quote.timestamp.isoformat()
    except MarketDataError:
        start, end = default_history_range()
        history = provider.get_stock_history(code, start, end)
        row = history.prices.iloc[-1]
        return float(row["close"]), f"{row['date']:%Y-%m-%d} 最近收盘"


st.title("我的持仓")
st.caption("账户基准币种：人民币（CNY）。美股按当前 USD/CNY 汇率折算；行情和汇率均可能延迟。")

try:
    settings = repository.get_account_settings()
    with st.expander("现金余额设置（CNY）"):
        with st.form("cash_form"):
            cash = st.number_input("当前现金余额（元）", min_value=0.0, value=float(settings.cash_balance), step=100.0)
            if st.form_submit_button("保存现金余额"):
                repository.update_cash_balance(float(cash))
                st.success("现金余额已更新。")
                st.rerun()

    all_positions = calculate_positions(repository.list_all(), include_closed=True)
    active_positions = [position for position in all_positions if position.quantity > 0]
    if not active_positions:
        st.info("当前没有持仓。请先到“交易记录”页面添加第一笔买入交易。")
        st.button("AI 分析我的投资组合", disabled=True, help="即将推出")
        st.stop()

    if st.button("刷新持仓行情"):
        latest_price.clear()
        st.rerun()
    with st.spinner("正在更新持仓行情…"):
        prices = {position.stock_code: latest_price(position.stock_code) for position in active_positions}
        usd_positions = any(not position.stock_code.isdigit() for position in all_positions)
        usd_cny = latest_price("CNY=X")[0] if usd_positions else None

    valued = value_positions(active_positions, prices, usd_cny)
    summary = summarize_portfolio(valued, all_positions, settings.cash_balance, usd_cny)
    if usd_cny is not None:
        st.caption(f"USD/CNY 折算汇率：{usd_cny:.4f}｜汇率时间：{latest_price('CNY=X')[1]}")

    metrics = [
        ("总资产", summary.total_assets), ("持仓总市值", summary.total_market_value),
        ("现金余额", summary.cash_balance), ("浮动盈亏", summary.unrealized_pnl),
        ("已实现盈亏", summary.realized_pnl), ("总盈亏", summary.total_pnl),
        ("当前持仓数量", summary.position_count),
    ]
    display_metrics = [
        (label, str(int(value)), f"持仓标的数量：{int(value)}")
        if label == "当前持仓数量"
        else (label, currency_compact(value), f"精确金额：{currency_full(value)}")
        for label, value in metrics
    ]
    render_metric_grid(display_metrics, columns_per_row=4)

    left, right = st.columns(2)
    left.plotly_chart(allocation_chart(valued, settings.cash_balance), width="stretch")
    right.plotly_chart(market_value_chart(valued), width="stretch")
    left, right = st.columns(2)
    left.plotly_chart(pnl_amount_chart(valued), width="stretch")
    right.plotly_chart(pnl_percent_chart(valued), width="stretch")

    st.subheader("持仓明细")
    sort_by = st.selectbox("排序方式", ["持仓市值（高到低）", "收益率（高到低）"])
    valued.sort(key=lambda item: item.market_value_cny if sort_by.startswith("持仓") else item.unrealized_pnl_pct, reverse=True)
    table = pd.DataFrame([{
        "股票代码": item.stock_code, "股票名称": item.stock_name, "币种": item.currency,
        "当前数量": item.quantity, "平均成本(原币)": round(item.average_cost, 4),
        "最新价格(原币)": round(item.latest_price, 4), "价格时间": item.price_time,
        "持仓市值(CNY)": round(item.market_value_cny, 2), "浮动盈亏(CNY)": round(item.unrealized_pnl_cny, 2),
        "浮动收益率": percent(item.unrealized_pnl_pct), "已实现盈亏(CNY)": round(item.realized_pnl_cny, 2),
        "总盈亏(CNY)": round(item.total_pnl_cny, 2),
    } for item in valued])
    event = st.dataframe(table, width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        selected = valued[event.selection.rows[0]]
        st.session_state["stock_code"] = selected.stock_code
        st.switch_page("pages/1_stock_analysis.py")

    st.divider()
    st.button("AI 分析我的投资组合", disabled=True, help="即将推出")
    st.caption("即将推出。V0.1 不调用大模型 API，也不生成投资建议。")
except (DatabaseError, MarketDataError, PortfolioValidationError, ValueError) as exc:
    st.error(str(exc))
except Exception:
    LOGGER.exception("Unexpected portfolio dashboard error")
    st.error("持仓页面处理失败，详细错误已记录。")
