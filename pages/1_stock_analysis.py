"""Stock analysis page."""

from datetime import datetime
import logging

import streamlit as st

from components.candlestick_chart import create_candlestick_figure
from components.charts import make_boll_chart, make_line_chart, make_macd_chart
from components.indicator_cards import render_status_cards
from components.stock_summary import render_stock_summary
from services.indicators import IndicatorStatus, latest_statuses
from services.analysis_cache import cached_calculate_indicators, cached_prepare_chart_data
from services.chart_data import ChartDataError, filter_data_by_period
from services.market_data import LatestQuote, MarketDataError, StockHistory, YahooMarketDataProvider, full_history_range
from utils.validators import validate_security_symbol
from utils.logging_config import configure_logging
from utils.i18n import current_language, language_selector, tr

try:
    from utils.i18n import interval_code, interval_labels
except ImportError:  # Streamlit may retain an older imported i18n module during hot reload.
    def interval_labels() -> list[str]:
        return ["Daily", "Weekly", "Monthly"] if current_language() == "en" else ["日K", "周K", "月K"]

    def interval_code(label: str) -> str:
        return {"Daily": "日K", "Weekly": "周K", "Monthly": "月K"}.get(label, label)

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="股票分析 | TradeBot", page_icon="📊", layout="wide")


@st.cache_data(ttl=1800, show_spinner=False)
def load_history(code: str, adjustment: str = "auto", history_scope: str = "MAX") -> StockHistory:
    """Cache complete history; explicit arguments form stable cache keys."""
    start, end = full_history_range()
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
    language_selector()
    st.caption(tr("分钟行情每10秒刷新｜日线缓存30分钟", "Minute quote: 10s refresh | Daily cache: 30m"))
    if st.button(tr("刷新行情", "Refresh quotes"), width="stretch"):
        load_history.clear()
        load_latest_quote.clear()
        cached_calculate_indicators.clear()
        cached_prepare_chart_data.clear()
        st.session_state["market_refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.rerun()
    st.caption(f"{tr('最近刷新', 'Last refresh')}: {st.session_state.get('market_refreshed_at', tr('尚未手动刷新', 'Not manually refreshed'))}")
    st.divider()
    st.caption(tr("仅用于数据展示，不构成投资建议。", "For data display only. Not investment advice."))

st.title(tr("股票分析 · A 股 / 美股", "Stock Analysis · A-shares / US"))
code_input = st.text_input(
    tr("证券代码", "Ticker symbol"),
    value=st.session_state.get("stock_code", "000938"),
    max_chars=15,
    placeholder=tr("A 股：000938｜美股：AAPL、TSLA、BRK-B", "A-share: 000938 | US: AAPL, TSLA, BRK-B"),
    help=tr("六位数字映射为A股，字母代码按Yahoo美股查询。", "Six digits map to A-shares; letters use Yahoo US tickers."),
)

if st.button(tr("查询", "Search"), type="primary") or code_input:
    try:
        code = validate_security_symbol(code_input)
        st.session_state["stock_code"] = code
        with st.spinner(tr("正在获取历史行情…", "Loading historical quotes…")):
            stock = load_history(code)
        render_quasi_realtime_summary(stock)
        period = st.segmented_control(
            tr("K线显示周期", "Chart range"), options=["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"],
            default="3M", key="stock_chart_period",
        ) or "3M"
        period_context = (period, current_language())
        if st.session_state.get("_stock_interval_context") != period_context:
            default_code = "周K" if period in ("3Y", "5Y", "MAX") else "日K"
            st.session_state["stock_chart_interval_display"] = {
                "日K": tr("日K","Daily"), "周K": tr("周K","Weekly"), "月K": tr("月K","Monthly")
            }[default_code]
            st.session_state["_stock_interval_context"] = period_context
        interval_display = st.segmented_control(
            tr("K线粒度", "Interval"), options=interval_labels(), key="stock_chart_interval_display",
        ) or interval_labels()[0]
        interval = interval_code(interval_display)
        data = cached_prepare_chart_data(stock.prices, interval)
        statuses = latest_statuses(data)
        render_status_cards([statuses[key] for key in ("trend", "macd", "rsi")])
        chart_data = filter_data_by_period(data, period)
        st.plotly_chart(
            create_candlestick_figure(
                chart_data, period, f"{stock.name}（{code}） {tr('K线与成交量','Price and Volume')}", interval=interval_display
            ),
            width="stretch", config={"scrollZoom": True, "displaylogo": False},
        )

        st.subheader(tr("技术指标", "Technical Indicators"))
        selected_indicator = st.segmented_control(
            tr("指标视图", "Indicator view"), options=["MACD", "RSI", "KDJ", "BOLL", tr("波动率", "Volatility")],
            default="MACD", key="stock_indicator_view",
        ) or "MACD"
        row = data.iloc[-1]
        if selected_indicator == "MACD":
            render_status_cards([statuses["macd"], statuses["volume"]])
            st.metric(tr("最新 DIF / DEA / 柱体","Latest DIF / DEA / Histogram"), f"{row['dif']:.3f} / {row['dea']:.3f} / {row['macd_hist']:.3f}")
            st.plotly_chart(make_macd_chart(chart_data), width="stretch")
        elif selected_indicator == "RSI":
            render_status_cards([statuses["rsi"]])
            st.metric(tr("最新 RSI14","Latest RSI14"), _number(row["rsi14"]))
            st.plotly_chart(make_line_chart(chart_data, ["rsi14"], ["RSI14"], "RSI（Wilder 14）", [30, 70]), width="stretch")
        elif selected_indicator == "KDJ":
            render_status_cards([] if row[["k", "d", "j"]].isna().all() else [IndicatorStatus("KDJ", "客观数值", f"K {_number(row['k'])}｜D {_number(row['d'])}｜J {_number(row['j'])}")])
            st.metric(tr("最新 K / D / J","Latest K / D / J"), f"{_number(row['k'])} / {_number(row['d'])} / {_number(row['j'])}")
            st.plotly_chart(make_line_chart(chart_data, ["k", "d", "j"], ["K", "D", "J"], "KDJ（9, 3, 3）", [20, 80]), width="stretch")
        elif selected_indicator == "BOLL":
            render_status_cards([statuses["boll"]])
            st.metric(tr("最新上轨 / 中轨 / 下轨","Latest Upper / Middle / Lower"), f"{_number(row['boll_upper'])} / {_number(row['boll_mid'])} / {_number(row['boll_lower'])}")
            st.plotly_chart(make_boll_chart(chart_data), width="stretch")
        else:
            render_status_cards([statuses["volatility"]])
            value = row["volatility20"]
            st.metric(tr("最新 20 日年化波动率","Latest 20-session Annualized Volatility"), "-" if value != value else f"{value:.2%}")
            st.plotly_chart(make_line_chart(chart_data, ["volatility20"], [tr("20日年化波动率","20-session annualized volatility")], tr("20 日历史波动率","20-session Historical Volatility")), width="stretch")
        st.caption(tr("所有状态来自固定可解释规则，不构成买卖建议。数据源：Yahoo Finance。", "All statuses use fixed explainable rules and are not trading advice. Source: Yahoo Finance."))
    except (ValueError, MarketDataError, ChartDataError) as exc:
        st.error(str(exc))
    except Exception:
        LOGGER.exception("Unexpected stock analysis error")
        st.error(tr("页面处理失败，请稍后重试；详细信息已写入日志。", "Page processing failed. Try again later; details were written to the log."))
