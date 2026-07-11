"""Portfolio allocation and P&L charts."""

import plotly.express as px
import plotly.graph_objects as go

from services.portfolio_service import ValuedPosition


def allocation_chart(positions: list[ValuedPosition], cash: float) -> go.Figure:
    labels = [f"{item.stock_name} ({item.stock_code})" for item in positions] + ["现金"]
    values = [item.market_value_cny for item in positions] + [cash]
    fig = px.pie(names=labels, values=values, hole=0.58, title="资产结构（CNY）")
    fig.update_layout(height=430, margin={"l": 20, "r": 20, "t": 55, "b": 20})
    return fig


def market_value_chart(positions: list[ValuedPosition]) -> go.Figure:
    return _bar(positions, "market_value_cny", "持仓市值（CNY）", "市值（元）", False)


def pnl_amount_chart(positions: list[ValuedPosition]) -> go.Figure:
    return _bar(positions, "unrealized_pnl_cny", "浮动盈亏金额（CNY）", "盈亏（元）", True)


def pnl_percent_chart(positions: list[ValuedPosition]) -> go.Figure:
    return _bar(positions, "unrealized_pnl_pct", "浮动收益率", "收益率（%）", True)


def _bar(positions: list[ValuedPosition], field: str, title: str, y_title: str, signed: bool) -> go.Figure:
    labels = [f"{item.stock_name}<br>{item.stock_code}" for item in positions]
    values = [getattr(item, field) for item in positions]
    colors = ["#16a34a" if value >= 0 else "#dc2626" for value in values] if signed else "#3b82f6"
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
    fig.update_layout(title=title, yaxis_title=y_title, height=410, margin={"l": 20, "r": 20, "t": 55, "b": 20})
    return fig
