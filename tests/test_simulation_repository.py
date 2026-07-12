"""Simulation schema migration and isolation tests."""

import sqlite3
from datetime import date

import pytest

from database.db import TransactionRepository
from simulation.fee_config import SimulationFeeConfig
from simulation.models import SimulationOrder
from simulation.repository import SimulationRepository


def test_migration_is_idempotent_and_isolated(tmp_path) -> None:
    path = tmp_path / "tradebot.db"
    real = TransactionRepository(path)
    simulation = SimulationRepository(path)
    account = simulation.create_account("历史练习", 100_000, date(2024, 1, 2), SimulationFeeConfig())
    simulation.add_order(SimulationOrder(account.id, "000001", "平安银行", "BUY", 100, account.current_date))
    SimulationRepository(path)
    assert len(simulation.list_accounts()) == 1
    assert real.list_all() == []
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"simulation_accounts", "simulation_orders", "simulation_daily_snapshots"}.issubset(tables)
        assert connection.execute("PRAGMA user_version").fetchone()[0] >= 2


def test_fee_config_is_centralized() -> None:
    config = SimulationFeeConfig(commission_rate=0.001, minimum_commission=5, sell_tax_rate=0.0005, slippage_bps=10)
    assert config.execution_price(10, "BUY") == pytest.approx(10.01)
    assert config.execution_price(10, "SELL") == pytest.approx(9.99)
    assert config.fees("BUY", 10, 100) == (5, 0)
    commission, tax = config.fees("SELL", 10, 1000)
    assert commission == 10
    assert tax == 5
