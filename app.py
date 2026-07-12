"""TradeBot V0.1 Streamlit entry point."""

import streamlit as st

from utils.logging_config import configure_logging
from utils.i18n import language_selector, tr

configure_logging()

st.set_page_config(page_title="TradeBot V0.1", page_icon="📈", layout="wide")

st.title("TradeBot V0.1")
st.caption(tr("A 股 / 美股技术分析与个人持仓管理", "A-share / US stock analysis and portfolio management"))
st.info(tr("请从左侧导航进入股票分析、持仓、交易记录或模拟盘。", "Use the sidebar to open Analysis, Portfolio, Transactions, or Simulation."))

with st.sidebar:
    st.markdown("## TradeBot")
    language_selector()
    st.caption(tr("本地金融数据工作台", "Local financial data workspace"))
    st.divider()
    st.caption(tr("本应用仅用于数据展示和个人投资记录，不构成任何投资建议。行情数据可能存在延迟。", "For data display and personal records only. Not investment advice. Quotes may be delayed."))
