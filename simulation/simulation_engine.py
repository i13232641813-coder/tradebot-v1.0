"""Historical daily replay matching engine.

No Streamlit calls, broker connections, minute data, limit orders or AI logic belong here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import pandas as pd

from simulation.fee_config import SimulationFeeConfig
from simulation.market_clock import HistoricalMarketClock, MarketClockError
from simulation.models import SimulationOrder, SimulationPosition, SimulationSnapshot
from simulation.repository import SimulationRepository


class SimulationValidationError(ValueError):
    pass


@dataclass
class _PositionState:
    name: str
    quantity: int = 0
    average_cost: float = 0.0
    realized_pnl: float = 0.0
    bought_by_date: dict[date, int] | None = None

    def __post_init__(self) -> None:
        if self.bought_by_date is None:
            self.bought_by_date = defaultdict(int)


class SimulationEngine:
    def __init__(self, repository: SimulationRepository) -> None:
        self.repository = repository

    def submit_order(self, order: SimulationOrder) -> SimulationOrder:
        """Validate a close-of-day market order and persist it as PENDING."""
        account = self.repository.get_account(order.account_id)
        if order.submitted_date != account.current_date:
            raise SimulationValidationError("订单提交日期必须等于当前模拟日期")
        if order.side not in ("BUY", "SELL"):
            raise SimulationValidationError("订单方向必须是 BUY 或 SELL")
        if order.quantity <= 0:
            raise SimulationValidationError("订单数量必须为正整数")
        if order.side == "BUY" and order.quantity % 100 != 0:
            raise SimulationValidationError("模拟买入数量必须为 100 股的整数倍")
        if not 1 <= order.confidence_level <= 5:
            raise SimulationValidationError("信心等级必须在 1 到 5 之间")
        if order.side == "SELL":
            position = self.position_map(order.account_id, account.current_date).get(order.stock_code)
            sellable = position.sellable_quantity if position else 0
            pending_sells = sum(
                item.quantity for item in self.repository.list_orders(order.account_id, "PENDING")
                if item.side == "SELL" and item.stock_code == order.stock_code
            )
            if order.quantity > sellable - pending_sells:
                raise SimulationValidationError(
                    f"可卖数量不足：可卖 {sellable} 股，已有待处理卖单 {pending_sells} 股"
                )
        return self.repository.add_order(order)

    def cancel_order(self, account_id: int, order_id: int) -> None:
        self.repository.cancel_order(order_id, account_id)

    def positions(self, account_id: int, as_of: date) -> list[SimulationPosition]:
        return list(self.position_map(account_id, as_of).values())

    def position_map(self, account_id: int, as_of: date) -> dict[str, SimulationPosition]:
        states: dict[str, _PositionState] = defaultdict(lambda: _PositionState(name=""))
        orders = [item for item in self.repository.list_orders(account_id, "FILLED") if item.execution_date and item.execution_date <= as_of]
        orders.sort(key=lambda item: (item.execution_date, item.id or 0))
        for order in orders:
            assert order.fill_price is not None and order.execution_date is not None
            state = states[order.stock_code]
            state.name = order.stock_name
            if order.side == "BUY":
                new_quantity = state.quantity + order.quantity
                state.average_cost = (
                    state.quantity * state.average_cost
                    + order.quantity * order.fill_price + order.commission
                ) / new_quantity
                state.quantity = new_quantity
                state.bought_by_date[order.execution_date] += order.quantity
            else:
                state.realized_pnl += order.quantity * (order.fill_price - state.average_cost) - order.commission - order.tax
                state.quantity -= order.quantity
                self._consume_buys(state.bought_by_date, order.quantity)
                if state.quantity == 0:
                    state.average_cost = 0.0
        result: dict[str, SimulationPosition] = {}
        for code, state in states.items():
            if state.quantity <= 0:
                continue
            sellable = sum(quantity for bought_date, quantity in state.bought_by_date.items() if bought_date < as_of)
            result[code] = SimulationPosition(code, state.name, state.quantity, sellable, state.average_cost, state.realized_pnl)
        return result

    def advance_to_next_day(
        self,
        account_id: int,
        calendar: HistoricalMarketClock,
        bars_by_code: dict[str, pd.DataFrame],
    ) -> SimulationSnapshot:
        """Advance exactly one session, execute pending orders at open, and snapshot at close."""
        account = self.repository.get_account(account_id)
        next_date = calendar.next_trading_date(account.current_date)
        config = SimulationFeeConfig(
            account.commission_rate, account.minimum_commission,
            account.sell_tax_rate, account.slippage_bps,
        )
        cash = account.cash_balance
        for order in self.repository.list_orders(account_id, "PENDING"):
            if order.submitted_date >= next_date:
                continue
            try:
                bar = self._bar_for(bars_by_code, order.stock_code, next_date)
                fill_price = config.execution_price(float(bar["open"]), order.side)
                commission, tax = config.fees(order.side, fill_price, order.quantity)
                if order.side == "BUY":
                    required = fill_price * order.quantity + commission
                    if required > cash + 1e-9:
                        raise SimulationValidationError(f"资金不足：需要 {required:.2f}，可用 {cash:.2f}")
                    cash -= required
                else:
                    positions = self.position_map(account_id, next_date)
                    position = positions.get(order.stock_code)
                    sellable = position.sellable_quantity if position else 0
                    if order.quantity > sellable:
                        raise SimulationValidationError(f"可卖数量不足：可卖 {sellable} 股")
                    cash += fill_price * order.quantity - commission - tax
                self.repository.set_order_result(
                    order.id or 0, "FILLED", next_date, fill_price, commission, tax
                )
            except (SimulationValidationError, MarketClockError, KeyError, ValueError) as exc:
                self.repository.set_order_result(
                    order.id or 0, "REJECTED", next_date, rejection_reason=str(exc)
                )

        positions = self.positions(account_id, next_date)
        realized = self._total_realized(account_id, next_date)
        market_value = 0.0
        unrealized = 0.0
        for position in positions:
            close = float(self._bar_for(bars_by_code, position.stock_code, next_date)["close"])
            market_value += position.quantity * close
            unrealized += position.quantity * (close - position.average_cost)
        total_assets = cash + market_value
        previous = self.repository.list_snapshots(account_id)
        previous_assets = previous[-1].total_assets if previous else account.initial_cash
        peak = max([account.initial_cash, *(item.total_assets for item in previous), total_assets])
        daily_return = total_assets / previous_assets - 1 if previous_assets else 0.0
        cumulative_return = total_assets / account.initial_cash - 1
        current_drawdown = total_assets / peak - 1 if peak else 0.0
        prior_max_drawdown = min((item.max_drawdown for item in previous), default=0.0)
        max_drawdown = min(prior_max_drawdown, current_drawdown)
        snapshot = SimulationSnapshot(
            account_id, next_date, cash, market_value, total_assets, unrealized, realized,
            cumulative_return, daily_return, current_drawdown, max_drawdown,
        )
        self.repository.update_account_state(account_id, cash, next_date, realized)
        self.repository.upsert_snapshot(snapshot)
        return snapshot

    def create_initial_snapshot(self, account_id: int) -> SimulationSnapshot:
        account = self.repository.get_account(account_id)
        snapshot = SimulationSnapshot(
            account.id, account.current_date, account.cash_balance, 0.0, account.cash_balance,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        )
        self.repository.upsert_snapshot(snapshot)
        return snapshot

    def _total_realized(self, account_id: int, as_of: date) -> float:
        states: dict[str, float] = defaultdict(float)
        costs: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for order in self.repository.list_orders(account_id, "FILLED"):
            if not order.execution_date or order.execution_date > as_of or order.fill_price is None:
                continue
            quantity, average = costs[order.stock_code]
            if order.side == "BUY":
                new_quantity = quantity + order.quantity
                average = (quantity * average + order.quantity * order.fill_price + order.commission) / new_quantity
                costs[order.stock_code] = (new_quantity, average)
            else:
                states[order.stock_code] += order.quantity * (order.fill_price - average) - order.commission - order.tax
                costs[order.stock_code] = (quantity - order.quantity, average if quantity != order.quantity else 0.0)
        return sum(states.values())

    @staticmethod
    def _consume_buys(buys: dict[date, int], quantity: int) -> None:
        remaining = quantity
        for bought_date in sorted(buys):
            used = min(buys[bought_date], remaining)
            buys[bought_date] -= used
            remaining -= used
            if remaining == 0:
                break

    @staticmethod
    def _bar_for(bars_by_code: dict[str, pd.DataFrame], code: str, trading_date: date) -> pd.Series:
        if code not in bars_by_code:
            raise KeyError(f"缺少 {code} 的行情")
        return HistoricalMarketClock(bars_by_code[code]).bar_on(trading_date)
