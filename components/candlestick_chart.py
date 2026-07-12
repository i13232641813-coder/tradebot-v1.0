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
from utils.i18n import tr

MA_COLORS = {5: "#f59e0b", 10: "#3b82f6", 20: "#8b5cf6", 60: "#94a3b8"}


def create_candlestick_figure(
    visible: pd.DataFrame,
    period: str,
    title: str,
    interval: str = "日K",
    show_ma: Sequence[int] = (5, 10, 20, 60),
    show_boll: bool = False,
    show_volume_ma: bool = True,
    include_volume_panel: bool = True,
    height: int = 720,
) -> go.Figure:
    """Create a fixed-height figure using only the selected visible window."""
    overlays = [f"ma{window}" for window in show_ma if f"ma{window}" in visible.columns]
    if show_boll:
        overlays.extend(column for column in ("boll_upper", "boll_lower") if column in visible.columns)
    price_range = calculate_price_axis_range(visible, overlays)
    volume_range = calculate_volume_axis_range(visible) if include_volume_panel else None
    required = ["date", "open", "high", "low", "close", "volume"]
    boll_columns = ("boll_upper", "boll_mid", "boll_lower") if show_boll else ()
    requested_columns = dict.fromkeys((*required, "change_pct", *overlays, *boll_columns, "vol_ma5", "vol_ma10"))
    data = visible.loc[:, [column for column in requested_columns if column in visible.columns]]
    change_pct = (
        pd.to_numeric(data["change_pct"], errors="coerce")
        if "change_pct" in data.columns
        else pd.to_numeric(data["close"], errors="coerce").pct_change() * 100
    )
    hover = [
        f"{tr('日期','Date')}: {pd.Timestamp(day):%Y-%m-%d}<br>{tr('开盘','Open')}: {open_:,.2f}<br>{tr('最高','High')}: {high:,.2f}"
        f"<br>{tr('最低','Low')}: {low:,.2f}<br>{tr('收盘','Close')}: {close:,.2f}<br>{tr('涨跌幅','Change')}: {pct:.2f}%"
        f"<br>{tr('成交量','Volume')}: {volume:,.0f}"
        for day, open_, high, low, close, pct, volume in zip(
            data["date"], data["open"], data["high"], data["low"], data["close"],
            change_pct.fillna(0), data["volume"],
        )
    ]
    colors = ["#16a34a" if close >= open_ else "#dc2626" for open_, close in zip(data["open"], data["close"])]
    fig = make_subplots(
        rows=2 if include_volume_panel else 1, cols=1,
        shared_xaxes=include_volume_panel, vertical_spacing=0.025,
        row_heights=[0.75, 0.25] if include_volume_panel else [1.0],
    )
    fig.add_trace(go.Candlestick(
        x=data["date"], open=data["open"], high=data["high"], low=data["low"], close=data["close"],
        name=tr("日K","Candles"), text=hover, hoverinfo="text",
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
    if show_boll and all(column in data.columns for column in ("boll_upper", "boll_mid", "boll_lower")):
        for column, name, dash in (
            ("boll_upper", tr("BOLL上轨","BOLL Upper"), "dot"),
            ("boll_mid", tr("BOLL中轨","BOLL Middle"), "dash"),
            ("boll_lower", tr("BOLL下轨","BOLL Lower"), "dot"),
        ):
            fig.add_trace(go.Scatter(
                x=data["date"], y=data[column], name=name,
                line={"width": 1.1, "color": "#a78bfa", "dash": dash},
                hovertemplate=f"{name}：%{{y:.2f}}<extra></extra>",
            ), row=1, col=1)
    if include_volume_panel:
        fig.add_trace(go.Bar(
            x=data["date"], y=data["volume"], name=tr("成交量","Volume"), marker_color=colors,
            hovertemplate=f"{tr('成交量','Volume')}: %{{y:,.0f}}<extra></extra>",
        ), row=2, col=1)
    if include_volume_panel and show_volume_ma:
        for window in (5, 10):
            column = f"vol_ma{window}"
            if column in data.columns and data[column].notna().any():
                fig.add_trace(go.Scatter(
                    x=data["date"], y=data[column], name=f"VOL MA{window}",
                    line={"width": 1.2}, hovertemplate=f"VOL MA{window}：%{{y:,.0f}}<extra></extra>",
                ), row=2, col=1)
    breaks = non_trading_dates(data)
    fig.update_xaxes(rangebreaks=[{"values": breaks}], showspikes=True, spikemode="across", spikesnap="cursor")
    fig.update_yaxes(range=list(price_range), fixedrange=False, title_text=tr("价格","Price"), row=1, col=1)
    if volume_range is not None:
        fig.update_yaxes(range=list(volume_range), fixedrange=False, title_text=tr("成交量","Volume"), row=2, col=1)
    fig.update_layout(
        title=f"{title}｜{period}｜{interval}", height=height, hovermode="x unified",
        xaxis_rangeslider_visible=False, dragmode="pan", uirevision=None,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        margin={"l": 20, "r": 20, "t": 75, "b": 20},
    )
    return fig
