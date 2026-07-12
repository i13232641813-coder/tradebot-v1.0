"""Historical replay matching and account valuation tests."""

from datetime import date

import pandas as pd
import pytest

from simulation.fee_config import SimulationFeeConfig
from simulation.market_clock import HistoricalMarketClock, history_request_start
from simulation.models import SimulationOrder
from simulation.repository import SimulationRepository
from simulation.simulation_engine import SimulationEngine, SimulationValidationError
from services.indicators import calculate_indicators


def bars() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        "open": [10, 11, 12, 11], "high": [11, 12, 13, 12], "low": [9, 10, 11, 10],
        "close": [10.5, 11.5, 12.5, 11.5], "volume": [1000] * 4,
    })


def setup_engine(tmp_path, cash=100_000, config=None):
    repository = SimulationRepository(tmp_path / "simulation.db")
    account = repository.create_account("测试账户", cash, date(2024, 1, 2), config or SimulationFeeConfig(0, 0, 0, 0))
    engine = SimulationEngine(repository)
    engine.create_initial_snapshot(account.id)
    return repository, account, engine


def order(account_id, side, quantity, submitted=date(2024, 1, 2)):
    return SimulationOrder(account_id, "000001", "平安银行", side, quantity, submitted)


def test_no_future_data_leakage() -> None:
    clock = HistoricalMarketClock(bars())
    visible = clock.visible_bars(date(2024, 1, 3))
    assert visible["date"].max() == date(2024, 1, 3)
    assert len(visible) == 2
    assert clock.next_trading_date(date(2024, 1, 3)) == date(2024, 1, 4)


def test_replay_indicators_are_calculated_after_future_filtering() -> None:
    clock = HistoricalMarketClock(bars())
    visible = clock.visible_bars(date(2024, 1, 3))
    indicators = calculate_indicators(visible)
    assert len(indicators) == 2
    assert indicators["date"].max() == date(2024, 1, 3)
    assert indicators["ma5"].isna().all()


def test_history_request_uses_earliest_a_share_date() -> None:
    requested = history_request_start(date(2026, 6, 1))
    assert requested == date(1990, 1, 1)


def test_order_executes_next_day_open(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path)
    created = engine.submit_order(order(account.id, "BUY", 100))
    assert created.status == "PENDING"
    snapshot = engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    filled = repository.get_order(created.id)
    assert filled.status == "FILLED"
    assert filled.execution_date == date(2024, 1, 3)
    assert filled.fill_price == pytest.approx(11)
    assert snapshot.cash_balance == pytest.approx(98_900)


def test_insufficient_cash_rejects_order(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path, cash=1_000)
    created = engine.submit_order(order(account.id, "BUY", 100))
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    rejected = repository.get_order(created.id)
    assert rejected.status == "REJECTED"
    assert "资金不足" in rejected.rejection_reason
    assert repository.get_account(account.id).cash_balance == 1_000


def test_buy_lot_and_oversell_validation(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path)
    with pytest.raises(SimulationValidationError, match="100 股"):
        engine.submit_order(order(account.id, "BUY", 50))
    with pytest.raises(SimulationValidationError, match="可卖数量不足"):
        engine.submit_order(order(account.id, "SELL", 100))
    assert repository.list_orders(account.id) == []


def test_a_share_t_plus_one(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path)
    engine.submit_order(order(account.id, "BUY", 100))
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    account = repository.get_account(account.id)
    position = engine.positions(account.id, account.current_date)[0]
    assert position.quantity == 100
    assert position.sellable_quantity == 0
    with pytest.raises(SimulationValidationError, match="可卖数量不足"):
        engine.submit_order(order(account.id, "SELL", 100, account.current_date))
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    account = repository.get_account(account.id)
    assert engine.positions(account.id, account.current_date)[0].sellable_quantity == 100


def test_nav_return_and_drawdown(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path, cash=10_000)
    engine.submit_order(order(account.id, "BUY", 100))
    first = engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    assert first.total_assets == pytest.approx(10_050)
    second = engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    assert second.total_assets == pytest.approx(10_150)
    third = engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    assert third.total_assets == pytest.approx(10_050)
    assert third.current_drawdown == pytest.approx(10_050 / 10_150 - 1)
    assert third.max_drawdown == third.current_drawdown
    assert third.cumulative_return == pytest.approx(0.005)


def test_pending_order_can_be_cancelled(tmp_path) -> None:
    repository, account, engine = setup_engine(tmp_path)
    created = engine.submit_order(order(account.id, "BUY", 100))
    engine.cancel_order(account.id, created.id)
    assert repository.get_order(created.id).status == "CANCELLED"
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    assert engine.positions(account.id, date(2024, 1, 3)) == []


def test_fees_tax_and_realized_pnl(tmp_path) -> None:
    config = SimulationFeeConfig(commission_rate=0.001, minimum_commission=5, sell_tax_rate=0.001, slippage_bps=0)
    repository, account, engine = setup_engine(tmp_path, cash=10_000, config=config)
    buy = engine.submit_order(order(account.id, "BUY", 100))
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    filled_buy = repository.get_order(buy.id)
    assert filled_buy.commission == pytest.approx(5)
    engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    account = repository.get_account(account.id)
    sell = engine.submit_order(order(account.id, "SELL", 100, account.current_date))
    snapshot = engine.advance_to_next_day(account.id, HistoricalMarketClock(bars()), {"000001": bars()})
    filled_sell = repository.get_order(sell.id)
    assert filled_sell.fill_price == pytest.approx(11)
    assert filled_sell.commission == pytest.approx(5)
    assert filled_sell.tax == pytest.approx(1.1)
    # Buy cost includes 5 commission: average 11.05. Sell proceeds deduct 6.1.
    assert snapshot.realized_pnl == pytest.approx(100 * (11 - 11.05) - 5 - 1.1)
    assert snapshot.market_value == 0
