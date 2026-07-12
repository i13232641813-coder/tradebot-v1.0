"""Parameterized SQLite transaction repository."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Iterator

from database.models import AccountSettings, Transaction
from database.migrations import migrate_simulation_schema

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "tradebot.db"


class DatabaseError(RuntimeError):
    """Raised when a database operation fails."""


class TransactionRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise DatabaseError("数据库操作失败，请检查文件权限") from exc
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the local database and required tables on first use."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    trade_type TEXT NOT NULL CHECK (trade_type IN ('BUY', 'SELL')),
                    price REAL NOT NULL CHECK (price > 0),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    trade_date TEXT NOT NULL,
                    fee REAL NOT NULL DEFAULT 0 CHECK (fee >= 0),
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS account_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash_balance REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO account_settings (id, cash_balance) VALUES (1, 0);
            """)
            migrate_simulation_schema(connection)

    def list_all(self) -> list[Transaction]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transactions ORDER BY trade_date ASC, id ASC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def add(self, transaction: Transaction) -> Transaction:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO transactions
                   (stock_code, stock_name, trade_type, price, quantity, trade_date, fee, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (transaction.stock_code, transaction.stock_name, transaction.trade_type,
                 transaction.price, transaction.quantity, transaction.trade_date.isoformat(),
                 transaction.fee, transaction.note),
            )
            transaction_id = int(cursor.lastrowid)
        return self.get(transaction_id)

    def get(self, transaction_id: int) -> Transaction:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if row is None:
            raise DatabaseError("交易记录不存在")
        return self._from_row(row)

    def update(self, transaction: Transaction) -> Transaction:
        if transaction.id is None:
            raise DatabaseError("缺少交易 ID")
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE transactions SET stock_code=?, stock_name=?, trade_type=?, price=?,
                   quantity=?, trade_date=?, fee=?, note=? WHERE id=?""",
                (transaction.stock_code, transaction.stock_name, transaction.trade_type,
                 transaction.price, transaction.quantity, transaction.trade_date.isoformat(),
                 transaction.fee, transaction.note, transaction.id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("交易记录不存在")
        return self.get(transaction.id)

    def delete(self, transaction_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            if cursor.rowcount != 1:
                raise DatabaseError("交易记录不存在")

    def get_account_settings(self) -> AccountSettings:
        with self._connect() as connection:
            row = connection.execute("SELECT cash_balance, updated_at FROM account_settings WHERE id = 1").fetchone()
        if row is None:
            raise DatabaseError("账户设置不存在")
        return AccountSettings(float(row["cash_balance"]), datetime.fromisoformat(row["updated_at"]))

    def update_cash_balance(self, cash_balance: float) -> AccountSettings:
        if cash_balance < 0:
            raise ValueError("现金余额不能为负数")
        with self._connect() as connection:
            connection.execute(
                "UPDATE account_settings SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (float(cash_balance),),
            )
        return self.get_account_settings()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=int(row["id"]), stock_code=str(row["stock_code"]), stock_name=str(row["stock_name"]),
            trade_type=str(row["trade_type"]), price=float(row["price"]), quantity=int(row["quantity"]),
            trade_date=date.fromisoformat(row["trade_date"]), fee=float(row["fee"]), note=str(row["note"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
