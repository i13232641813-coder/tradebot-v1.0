"""Plotly financial and technical-indicator charts."""

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
from utils.i18n import tr


def _base_layout(fig: go.Figure, title: str, height: int = 430) -> go.Figure:
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    fig.update_layout(title=title, height=height, hovermode="x unified", margin={"l": 20, "r": 20, "t": 55, "b": 20}, legend={"orientation": "h"})
    return fig


def make_macd_chart(data: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["date"], y=data["dif"], name="DIF"))
    fig.add_trace(go.Scatter(x=data["date"], y=data["dea"], name="DEA"))
    colors = ["#16a34a" if value >= 0 else "#dc2626" for value in data["macd_hist"].fillna(0)]
    fig.add_trace(go.Bar(x=data["date"], y=data["macd_hist"], name="Histogram", marker_color=colors))
    return _base_layout(fig, "MACD（12, 26, 9）")


def make_volume_chart(data: pd.DataFrame) -> go.Figure:
    """Create a compact volume chart for the simulation workbench."""
    colors = ["#16a34a" if close >= open_ else "#dc2626" for open_, close in zip(data["open"], data["close"])]
    fig = go.Figure(go.Bar(
        x=data["date"], y=data["volume"], name=tr("成交量","Volume"), marker_color=colors,
        hovertemplate=f"{tr('成交量','Volume')}: %{{y:,.0f}}<extra></extra>",
    ))
    for window in (5, 10):
        column = f"vol_ma{window}"
        if column in data.columns and data[column].notna().any():
            fig.add_trace(go.Scatter(
                x=data["date"], y=data[column], name=f"VOL MA{window}",
                hovertemplate=f"VOL MA{window}：%{{y:,.0f}}<extra></extra>",
            ))
    return _base_layout(fig, tr("成交量","Volume"), height=260)


def make_line_chart(data: pd.DataFrame, columns: Sequence[str], names: Sequence[str], title: str, reference_lines: Sequence[float] = ()) -> go.Figure:
    fig = go.Figure()
    for column, name in zip(columns, names):
        fig.add_trace(go.Scatter(x=data["date"], y=data[column], name=name))
    for value in reference_lines:
        fig.add_hline(y=value, line_dash="dash", line_color="#94a3b8")
    return _base_layout(fig, title)


def make_boll_chart(data: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["date"], y=data["boll_upper"], name="上轨", line={"color": "#8b5cf6"}))
    fig.add_trace(go.Scatter(x=data["date"], y=data["boll_mid"], name="中轨", line={"color": "#3b82f6"}))
    fig.add_trace(go.Scatter(x=data["date"], y=data["boll_lower"], name="下轨", line={"color": "#8b5cf6"}, fill="tonexty", fillcolor="rgba(139,92,246,0.08)"))
    fig.add_trace(go.Scatter(x=data["date"], y=data["close"], name="收盘", line={"color": "#111827"}))
    return _base_layout(fig, "BOLL（20, 2）")
