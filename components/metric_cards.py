"""Responsive metric-card layout helpers."""

from collections.abc import Sequence

import streamlit as st


def render_metric_grid(
    metrics: Sequence[tuple[str, str, str | None]],
    columns_per_row: int = 5,
) -> None:
    """Split metrics across rows and expose full values through help text."""
    for start in range(0, len(metrics), columns_per_row):
        group = metrics[start:start + columns_per_row]
        columns = st.columns(len(group))
        for column, (label, value, help_text) in zip(columns, group):
            column.metric(label, value, help=help_text)
