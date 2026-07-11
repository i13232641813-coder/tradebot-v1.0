"""Domain models persisted by the local database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

TradeType = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Transaction:
    stock_code: str
    stock_name: str
    trade_type: TradeType
    price: float
    quantity: int
    trade_date: date
    fee: float = 0.0
    note: str = ""
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class Position:
    stock_code: str
    stock_name: str
    quantity: int
    average_cost: float
    realized_pnl: float


@dataclass(frozen=True)
class AccountSettings:
    cash_balance: float
    updated_at: datetime
