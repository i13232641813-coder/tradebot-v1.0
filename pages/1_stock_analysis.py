"""Stock analysis page."""

from datetime import datetime
import logging

import streamlit as st

from components.charts import make_boll_chart, make_candlestick_chart, make_line_chart, make_macd_chart
from components.indicator_cards import render_status_cards
from components.stock_summary import render_stock_summary
from services.indicators import IndicatorStatus, calculate_indicators, latest_statuses
from services.market_data import LatestQuote, MarketDataError, StockHistory, YahooMarketDataProvider, default_history_range
from utils.validators import validate_security_symbol
from utils.logging_config import configure_logging

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="股票分析 | TradeBot", page_icon="📊", layout="wide")


@st.cache_data(ttl=1800, show_spinner=False)
def load_history(code: str) -> StockHistory:
    start, end = default_history_range()
    return YahooMarketDataProvider().get_stock_history(code, start, end)


@st.cache_data(ttl=10, show_spinner=False)
def load_latest_quote(code: str) -> LatestQuote:
    """Cache the latest minute quote briefly to balance freshness and rate limits."""
    return YahooMarketDataProvider().get_latest_quote(code)


def _number(value: float) -> str:
    """Format an indicator value while tolerating NaN warm-up rows."""
    return "-" if value != value else f"{value:.2f}"


@st.fragment(run_every="10s")
def render_quasi_realtime_summary(stock: StockHistory) -> None:
    """Refresh only the quote cards every ten seconds, not the full page."""
    try:
        quote = load_latest_quote(stock.code)
        render_stock_summary(stock, quote)
    except MarketDataError as quote_error:
        st.warning(str(quote_error))
        render_stock_summary(stock)


with st.sidebar:
    st.markdown("## TradeBot")
    st.caption("分钟行情：每 10 秒自动刷新｜日线缓存：30 分钟")
    if st.button("刷新行情", width="stretch"):
        load_history.clear()
        load_latest_quote.clear()
        st.session_state["market_refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.rerun()
    st.caption(f"最近刷新：{st.session_state.get('market_refreshed_at', '本次启动后尚未手动刷新')}")
    st.divider()
    st.caption("本应用仅用于数据展示和个人投资记录，不构成任何投资建议。行情数据可能存在延迟。")

st.title("股票分析 · A 股 / 美股")
code_input = st.text_input(
    "证券代码",
    value=st.session_state.get("stock_code", "000938"),
    max_chars=15,
    placeholder="A 股：000938｜美股：AAPL、TSLA、BRK-B",
    help="六位数字自动映射为 A 股；字母代码按 Yahoo Finance 美股代码查询。",
)

if st.button("查询", type="primary") or code_input:
    try:
        code = validate_security_symbol(code_input)
        st.session_state["stock_code"] = code
        with st.spinner("正在获取前复权日线行情…"):
            stock = load_history(code)
        data = calculate_indicators(stock.prices)
        statuses = latest_statuses(data)
        render_quasi_realtime_summary(stock)
        render_status_cards([statuses[key] for key in ("trend", "macd", "rsi")])
        st.plotly_chart(make_candlestick_chart(data, f"{stock.name}（{code}）日K与成交量"), width="stretch")

        st.subheader("技术指标")
        macd_tab, rsi_tab, kdj_tab, boll_tab, volatility_tab = st.tabs(["MACD", "RSI", "KDJ", "BOLL", "波动率"])
        with macd_tab:
            render_status_cards([statuses["macd"], statuses["volume"]])
            st.metric("最新 DIF / DEA / 柱体", f"{data.iloc[-1]['dif']:.3f} / {data.iloc[-1]['dea']:.3f} / {data.iloc[-1]['macd_hist']:.3f}")
            st.plotly_chart(make_macd_chart(data), width="stretch")
        with rsi_tab:
            render_status_cards([statuses["rsi"]])
            st.metric("最新 RSI14", _number(data.iloc[-1]["rsi14"]))
            st.plotly_chart(make_line_chart(data, ["rsi14"], ["RSI14"], "RSI（Wilder 14）", [30, 70]), width="stretch")
        with kdj_tab:
            row = data.iloc[-1]
            render_status_cards([] if row[["k", "d", "j"]].isna().all() else [IndicatorStatus("KDJ", "客观数值", f"K {_number(row['k'])}｜D {_number(row['d'])}｜J {_number(row['j'])}")])
            st.metric("最新 K / D / J", f"{_number(row['k'])} / {_number(row['d'])} / {_number(row['j'])}")
            st.plotly_chart(make_line_chart(data, ["k", "d", "j"], ["K", "D", "J"], "KDJ（9, 3, 3）", [20, 80]), width="stretch")
        with boll_tab:
            render_status_cards([statuses["boll"]])
            row = data.iloc[-1]
            st.metric("最新上轨 / 中轨 / 下轨", f"{_number(row['boll_upper'])} / {_number(row['boll_mid'])} / {_number(row['boll_lower'])}")
            st.plotly_chart(make_boll_chart(data), width="stretch")
        with volatility_tab:
            render_status_cards([statuses["volatility"]])
            value = data.iloc[-1]["volatility20"]
            st.metric("最新 20 日年化波动率", "-" if value != value else f"{value:.2%}")
            st.plotly_chart(make_line_chart(data, ["volatility20"], ["20日年化波动率"], "20 日历史波动率"), width="stretch")
        st.caption("所有状态均来自固定、可解释规则，仅作客观描述，不构成买卖建议。数据来源：Yahoo Finance。")
    except (ValueError, MarketDataError) as exc:
        st.error(str(exc))
    except Exception:
        LOGGER.exception("Unexpected stock analysis error")
        st.error("页面处理失败，请稍后重试；详细信息已写入日志。")
