"""Cached technical-indicator preparation shared by analysis pages."""

import pandas as pd
import streamlit as st

from services.indicators import calculate_indicators
from services.chart_data import aggregate_ohlcv


@st.cache_data(ttl=1800, show_spinner=False)
def cached_calculate_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate indicators only when the normalized full input data changes."""
    return calculate_indicators(frame)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_prepare_chart_data(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregate the complete available history, then calculate indicators."""
    return calculate_indicators(aggregate_ohlcv(frame, interval))
