"""TradeBot V0.1 Streamlit entry point."""

import streamlit as st

from utils.logging_config import configure_logging

configure_logging()

st.set_page_config(page_title="TradeBot V0.1", page_icon="📈", layout="wide")

st.title("TradeBot V0.1")
st.caption("A 股 / 美股技术分析与个人持仓管理")
st.info("请从左侧导航进入「股票分析」「我的持仓」或「交易记录」。")

with st.sidebar:
    st.markdown("## TradeBot")
    st.caption("本地金融数据工作台")
    st.divider()
    st.caption("本应用仅用于数据展示和个人投资记录，不构成任何投资建议。行情数据可能存在延迟。")
