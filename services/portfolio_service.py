"""Moving-weighted-average position and realized P&L calculations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from database.models import Position, Transaction


class PortfolioValidationError(ValueError):
    """Raised when a transaction sequence would create an invalid position."""


@dataclass
class _PositionState:
    name: str
    quantity: int = 0
    average_cost: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class ValuedPosition:
    stock_code: str
    stock_name: str
    currency: str
    quantity: int
    average_cost: float
    latest_price: float
    price_time: str
    market_value_cny: float
    unrealized_pnl_cny: float
    unrealized_pnl_pct: float
    realized_pnl_cny: float
    total_pnl_cny: float


@dataclass(frozen=True)
class PortfolioSummary:
    cash_balance: float
    total_market_value: float
    total_assets: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    position_count: int


def calculate_positions(transactions: list[Transaction], include_closed: bool = False) -> list[Position]:
    """Replay transactions using moving weighted average cost."""
    states: dict[str, _PositionState] = defaultdict(lambda: _PositionState(name=""))
    ordered = sorted(transactions, key=lambda item: (item.trade_date, item.id if item.id is not None else 10**18))
    for transaction in ordered:
        _validate_transaction(transaction)
        state = states[transaction.stock_code]
        state.name = transaction.stock_name
        if transaction.trade_type == "BUY":
            new_quantity = state.quantity + transaction.quantity
            state.average_cost = (
                state.quantity * state.average_cost
                + transaction.quantity * transaction.price
                + transaction.fee
            ) / new_quantity
            state.quantity = new_quantity
        else:
            if transaction.quantity > state.quantity:
                raise PortfolioValidationError(
                    f"{transaction.stock_code} 在 {transaction.trade_date} 卖出 {transaction.quantity} 股，"
                    f"超过当时持仓 {state.quantity} 股"
                )
            state.realized_pnl += transaction.quantity * (transaction.price - state.average_cost) - transaction.fee
            state.quantity -= transaction.quantity
            if state.quantity == 0:
                state.average_cost = 0.0
    return [
        Position(code, state.name, state.quantity, state.average_cost, state.realized_pnl)
        for code, state in sorted(states.items()) if include_closed or state.quantity > 0
    ]


def position_for(transactions: list[Transaction], stock_code: str) -> Position | None:
    return next((position for position in calculate_positions(transactions, True) if position.stock_code == stock_code), None)


def unrealized_pnl(position: Position, latest_price: float) -> float:
    return position.quantity * (latest_price - position.average_cost)


def value_positions(
    positions: list[Position],
    prices: dict[str, tuple[float, str]],
    usd_cny: float | None = None,
) -> list[ValuedPosition]:
    """Value active positions in CNY while preserving native price fields."""
    valued: list[ValuedPosition] = []
    for position in positions:
        if position.quantity <= 0 or position.stock_code not in prices:
            continue
        latest_price, price_time = prices[position.stock_code]
        currency = "CNY" if position.stock_code.isdigit() else "USD"
        if currency == "USD" and (usd_cny is None or usd_cny <= 0):
            raise PortfolioValidationError("美元兑人民币汇率不可用，无法汇总美股资产")
        rate = 1.0 if currency == "CNY" else float(usd_cny)
        native_unrealized = unrealized_pnl(position, latest_price)
        market_value = position.quantity * latest_price * rate
        unrealized = native_unrealized * rate
        realized = position.realized_pnl * rate
        percentage = (latest_price - position.average_cost) / position.average_cost * 100 if position.average_cost else 0.0
        valued.append(ValuedPosition(
            position.stock_code, position.stock_name, currency, position.quantity,
            position.average_cost, latest_price, price_time, market_value, unrealized,
            percentage, realized, realized + unrealized,
        ))
    return valued


def summarize_portfolio(
    active: list[ValuedPosition],
    all_positions: list[Position],
    cash_balance: float,
    usd_cny: float | None = None,
) -> PortfolioSummary:
    """Build CNY account totals, including realized P&L from closed positions."""
    realized = 0.0
    for position in all_positions:
        rate = 1.0 if position.stock_code.isdigit() else usd_cny
        if rate is None:
            raise PortfolioValidationError("美元兑人民币汇率不可用，无法汇总美股盈亏")
        realized += position.realized_pnl * rate
    market_value = sum(item.market_value_cny for item in active)
    unrealized = sum(item.unrealized_pnl_cny for item in active)
    return PortfolioSummary(
        cash_balance, market_value, cash_balance + market_value, unrealized,
        realized, realized + unrealized, len(active),
    )


def _validate_transaction(transaction: Transaction) -> None:
    if transaction.price <= 0:
        raise PortfolioValidationError("成交价格必须大于 0")
    if not isinstance(transaction.quantity, int) or transaction.quantity <= 0:
        raise PortfolioValidationError("数量必须是正整数")
    if transaction.fee < 0:
        raise PortfolioValidationError("手续费不能为负数")
    if transaction.trade_date > date.today():
        raise PortfolioValidationError("交易日期不能晚于当前日期")
    if transaction.trade_type not in ("BUY", "SELL"):
        raise PortfolioValidationError("交易类型必须是 BUY 或 SELL")
