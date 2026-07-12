"""Technical status card rendering."""

import streamlit as st

from services.indicators import IndicatorStatus
from utils.i18n import status_text, tr


def render_status_cards(statuses: list[IndicatorStatus]) -> None:
    """Render compact neutral status cards."""
    if not statuses:
        st.info(tr("暂无可展示的指标状态。", "No indicator status available."))
        return
    columns = st.columns(min(3, len(statuses)))
    for index, status in enumerate(statuses):
        with columns[index % len(columns)]:
            st.markdown(f"**{status_text(status.title)}｜{status_text(status.state)}**")
            st.caption(status_text(status.detail))
