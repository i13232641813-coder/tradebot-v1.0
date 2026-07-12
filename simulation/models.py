"""Data structures for simulation accounts, orders and snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

OrderSide = Literal["BUY", "SELL"]
OrderStatus = Literal["PENDING", "FILLED", "REJECTED", "CANCELLED"]


@dataclass(frozen=True)
class SimulationAccount:
    id: int
    name: str
    initial_cash: float
    cash_balance: float
    start_date: date
    current_date: date
    commission_rate: float
    minimum_commission: float
    sell_tax_rate: float
    slippage_bps: float
    realized_pnl: float
    created_at: datetime


@dataclass(frozen=True)
class SimulationOrder:
    account_id: int
    stock_code: str
    stock_name: str
    side: OrderSide
    quantity: int
    submitted_date: date
    status: OrderStatus = "PENDING"
    reason: str = ""
    planned_holding_period: str = ""
    stop_loss_condition: str = ""
    target_condition: str = ""
    confidence_level: int = 3
    execution_date: date | None = None
    fill_price: float | None = None
    commission: float = 0.0
    tax: float = 0.0
    rejection_reason: str = ""
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class SimulationSnapshot:
    account_id: int
    snapshot_date: date
    cash_balance: float
    market_value: float
    total_assets: float
    unrealized_pnl: float
    realized_pnl: float
    cumulative_return: float
    daily_return: float
    current_drawdown: float
    max_drawdown: float
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class SimulationPosition:
    stock_code: str
    stock_name: str
    quantity: int
    sellable_quantity: int
    average_cost: float
    realized_pnl: float
