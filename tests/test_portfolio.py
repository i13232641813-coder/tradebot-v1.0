"""Moving-average portfolio and atomic CRUD tests."""

from datetime import date

import pytest

from database.db import TransactionRepository
from database.models import Transaction
from services.portfolio_service import PortfolioValidationError, calculate_positions, summarize_portfolio, unrealized_pnl, value_positions
from services.transaction_service import TransactionService


def trade(kind: str, price: float, quantity: int, fee: float = 0) -> Transaction:
    return Transaction("000938", "紫光股份", kind, price, quantity, date(2026, 1, 2), fee)


def test_required_buy_sell_case() -> None:
    position = calculate_positions([trade("BUY", 27, 200), trade("SELL", 31.5, 100)])[0]
    assert position.quantity == 100
    assert position.average_cost == pytest.approx(27)
    assert position.realized_pnl == pytest.approx(450)
    assert unrealized_pnl(position, 39.25) == pytest.approx(1225)
    assert position.realized_pnl + unrealized_pnl(position, 39.25) == pytest.approx(1675)


def test_two_buys_weighted_average() -> None:
    position = calculate_positions([trade("BUY", 10, 100), trade("BUY", 12, 100)])[0]
    assert position.quantity == 200
    assert position.average_cost == pytest.approx(11)


def test_fee_is_included_in_buy_cost_and_sell_pnl() -> None:
    position = calculate_positions([trade("BUY", 10, 100, 10), trade("SELL", 12, 50, 5)])[0]
    assert position.average_cost == pytest.approx(10.1)
    assert position.realized_pnl == pytest.approx(90)


def test_oversell_is_rejected_without_database_change(tmp_path) -> None:
    service = TransactionService(TransactionRepository(tmp_path / "test.db"))
    service.add(trade("BUY", 27, 100))
    with pytest.raises(PortfolioValidationError, match="超过当时持仓"):
        service.add(trade("SELL", 31.5, 200))
    assert len(service.list_all()) == 1


def test_edit_and_delete_revalidate_history(tmp_path) -> None:
    service = TransactionService(TransactionRepository(tmp_path / "test.db"))
    buy = service.add(trade("BUY", 10, 200))
    sell = service.add(trade("SELL", 12, 100))
    with pytest.raises(PortfolioValidationError):
        service.update(Transaction(**{**sell.__dict__, "quantity": 300}))
    with pytest.raises(PortfolioValidationError):
        service.delete(buy.id)
    assert len(service.list_all()) == 2


def test_dashboard_valuation_and_summary() -> None:
    positions = calculate_positions([trade("BUY", 27, 200), trade("SELL", 31.5, 100)], include_closed=True)
    valued = value_positions(positions, {"000938": (39.25, "2026-01-03")})
    summary = summarize_portfolio(valued, positions, cash_balance=1000)
    assert valued[0].market_value_cny == pytest.approx(3925)
    assert valued[0].unrealized_pnl_cny == pytest.approx(1225)
    assert summary.total_assets == pytest.approx(4925)
    assert summary.realized_pnl == pytest.approx(450)
    assert summary.total_pnl == pytest.approx(1675)


def test_us_position_uses_fx_conversion() -> None:
    us_trade = Transaction("AAPL", "Apple", "BUY", 100, 10, date(2026, 1, 2))
    positions = calculate_positions([us_trade], include_closed=True)
    valued = value_positions(positions, {"AAPL": (120, "latest")}, usd_cny=7.2)
    assert valued[0].market_value_cny == pytest.approx(8640)
    assert valued[0].unrealized_pnl_cny == pytest.approx(1440)


def test_cash_settings_persist(tmp_path) -> None:
    repository = TransactionRepository(tmp_path / "cash.db")
    repository.update_cash_balance(12345.67)
    assert repository.get_account_settings().cash_balance == pytest.approx(12345.67)
