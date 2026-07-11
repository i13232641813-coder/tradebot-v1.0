"""Technical status card rendering."""

import streamlit as st

from services.indicators import IndicatorStatus


def render_status_cards(statuses: list[IndicatorStatus]) -> None:
    """Render compact neutral status cards."""
    if not statuses:
        st.info("暂无可展示的指标状态。")
        return
    columns = st.columns(min(3, len(statuses)))
    for index, status in enumerate(statuses):
        with columns[index % len(columns)]:
            st.markdown(f"**{status.title}｜{status.state}**")
            st.caption(status.detail)
