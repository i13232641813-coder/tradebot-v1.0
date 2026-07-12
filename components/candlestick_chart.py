"""Efficient visible-window candlestick and volume figure."""

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from services.chart_data import (
    calculate_price_axis_range,
    calculate_volume_axis_range,
    non_trading_dates,
)

MA_COLORS = {5: "#f59e0b", 10: "#3b82f6", 20: "#8b5cf6", 60: "#94a3b8"}


def create_candlestick_figure(
    visible: pd.DataFrame,
    period: str,
    title: str,
    interval: str = "日K",
    show_ma: Sequence[int] = (5, 10, 20, 60),
    show_volume_ma: bool = True,
) -> go.Figure:
    """Create a fixed-height figure using only the selected visible window."""
    overlays = [f"ma{window}" for window in show_ma if f"ma{window}" in visible.columns]
    price_range = calculate_price_axis_range(visible, overlays)
    volume_range = calculate_volume_axis_range(visible)
    required = ["date", "open", "high", "low", "close", "volume"]
    data = visible.loc[:, [column for column in (*required, "change_pct", *overlays, "vol_ma5", "vol_ma10") if column in visible.columns]]
    change_pct = (
        pd.to_numeric(data["change_pct"], errors="coerce")
        if "change_pct" in data.columns
        else pd.to_numeric(data["close"], errors="coerce").pct_change() * 100
    )
    hover = [
        f"日期：{pd.Timestamp(day):%Y-%m-%d}<br>开盘：{open_:,.2f}<br>最高：{high:,.2f}"
        f"<br>最低：{low:,.2f}<br>收盘：{close:,.2f}<br>涨跌幅：{pct:.2f}%"
        f"<br>成交量：{volume:,.0f}"
        for day, open_, high, low, close, pct, volume in zip(
            data["date"], data["open"], data["high"], data["low"], data["close"],
            change_pct.fillna(0), data["volume"],
        )
    ]
    colors = ["#16a34a" if close >= open_ else "#dc2626" for open_, close in zip(data["open"], data["close"])]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.025,
        row_heights=[0.75, 0.25],
    )
    fig.add_trace(go.Candlestick(
        x=data["date"], open=data["open"], high=data["high"], low=data["low"], close=data["close"],
        name="日K", text=hover, hoverinfo="text",
        increasing={"line": {"color": "#22c55e"}, "fillcolor": "rgba(34,197,94,0.55)"},
        decreasing={"line": {"color": "#ef4444"}, "fillcolor": "rgba(239,68,68,0.55)"},
    ), row=1, col=1)
    for window in show_ma:
        column = f"ma{window}"
        if column in data.columns and data[column].notna().any():
            fig.add_trace(go.Scatter(
                x=data["date"], y=data[column], name=f"MA{window}",
                line={"width": 1.4, "color": MA_COLORS.get(window)}, connectgaps=False,
                hovertemplate=f"MA{window}：%{{y:.2f}}<extra></extra>",
            ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=data["date"], y=data["volume"], name="成交量", marker_color=colors,
        hovertemplate="成交量：%{y:,.0f}<extra></extra>",
    ), row=2, col=1)
    if show_volume_ma:
        for window in (5, 10):
            column = f"vol_ma{window}"
            if column in data.columns and data[column].notna().any():
                fig.add_trace(go.Scatter(
                    x=data["date"], y=data[column], name=f"VOL MA{window}",
                    line={"width": 1.2}, hovertemplate=f"VOL MA{window}：%{{y:,.0f}}<extra></extra>",
                ), row=2, col=1)
    breaks = non_trading_dates(data)
    fig.update_xaxes(rangebreaks=[{"values": breaks}], showspikes=True, spikemode="across", spikesnap="cursor")
    fig.update_yaxes(range=list(price_range), fixedrange=False, title_text="价格", row=1, col=1)
    fig.update_yaxes(range=list(volume_range), fixedrange=False, title_text="成交量", row=2, col=1)
    fig.update_layout(
        title=f"{title}｜{period}｜{interval}", height=720, hovermode="x unified",
        xaxis_rangeslider_visible=False, dragmode="pan", uirevision=None,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"l": 20, "r": 20, "t": 75, "b": 20},
    )
    return fig
