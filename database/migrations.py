"""Idempotent SQLite schema migrations."""

import sqlite3

SIMULATION_SCHEMA_VERSION = 2


def migrate_simulation_schema(connection: sqlite3.Connection) -> None:
    """Add isolated simulation tables without altering real portfolio tables."""
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS simulation_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            initial_cash REAL NOT NULL CHECK (initial_cash > 0),
            cash_balance REAL NOT NULL CHECK (cash_balance >= 0),
            start_date TEXT NOT NULL,
            current_date TEXT NOT NULL,
            commission_rate REAL NOT NULL,
            minimum_commission REAL NOT NULL,
            sell_tax_rate REAL NOT NULL,
            slippage_bps REAL NOT NULL,
            realized_pnl REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS simulation_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            submitted_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING','FILLED','REJECTED','CANCELLED')),
            reason TEXT NOT NULL DEFAULT '',
            planned_holding_period TEXT NOT NULL DEFAULT '',
            stop_loss_condition TEXT NOT NULL DEFAULT '',
            target_condition TEXT NOT NULL DEFAULT '',
            confidence_level INTEGER NOT NULL CHECK (confidence_level BETWEEN 1 AND 5),
            execution_date TEXT,
            fill_price REAL,
            commission REAL NOT NULL DEFAULT 0,
            tax REAL NOT NULL DEFAULT 0,
            rejection_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES simulation_accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sim_orders_account_status
            ON simulation_orders(account_id, status, submitted_date, id);
        CREATE TABLE IF NOT EXISTS simulation_daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            cash_balance REAL NOT NULL,
            market_value REAL NOT NULL,
            total_assets REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            cumulative_return REAL NOT NULL,
            daily_return REAL NOT NULL,
            current_drawdown REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, snapshot_date),
            FOREIGN KEY (account_id) REFERENCES simulation_accounts(id) ON DELETE CASCADE
        );
    """)
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    if current < SIMULATION_SCHEMA_VERSION:
        connection.execute(f"PRAGMA user_version = {SIMULATION_SCHEMA_VERSION}")
