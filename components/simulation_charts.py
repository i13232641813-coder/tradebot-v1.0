"""Charts for the isolated simulation account."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from simulation.models import SimulationSnapshot


def replay_price_chart(data: pd.DataFrame, code: str, name: str) -> go.Figure:
    """Render only the already-visible daily bars supplied by the page."""
    fig = go.Figure(go.Candlestick(
        x=data["date"], open=data["open"], high=data["high"],
        low=data["low"], close=data["close"], name="日K",
    ))
    fig.update_layout(
        title=f"{name}（{code}）历史回放｜截止 {data.iloc[-1]['date']}",
        height=520, xaxis_rangeslider_visible=False, hovermode="x unified",
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
    )
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    return fig


def equity_and_drawdown_chart(snapshots: list[SimulationSnapshot]) -> go.Figure:
    dates = [item.snapshot_date for item in snapshots]
    assets = [item.total_assets for item in snapshots]
    drawdowns = [item.current_drawdown * 100 for item in snapshots]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.08)
    fig.add_trace(go.Scatter(x=dates, y=assets, name="总资产", line={"color": "#3b82f6", "width": 2}), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=drawdowns, name="回撤", fill="tozeroy", line={"color": "#dc2626"}), row=2, col=1)
    fig.update_yaxes(title_text="净值（元）", row=1, col=1)
    fig.update_yaxes(title_text="回撤（%）", row=2, col=1)
    fig.update_layout(title="模拟账户净值与回撤", height=620, hovermode="x unified", margin={"l": 20, "r": 20, "t": 55, "b": 20})
    return fig
