"""SQLite repository dedicated to simulation data."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Iterator

from database.db import DEFAULT_DB_PATH, DatabaseError
from database.migrations import migrate_simulation_schema
from simulation.fee_config import SimulationFeeConfig
from simulation.models import SimulationAccount, SimulationOrder, SimulationSnapshot


class SimulationRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            migrate_simulation_schema(connection)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise DatabaseError("模拟盘数据库操作失败") from exc
        finally:
            connection.close()

    def create_account(self, name: str, initial_cash: float, start_date: date, config: SimulationFeeConfig) -> SimulationAccount:
        config.validate()
        if not name.strip():
            raise ValueError("模拟账户名称不能为空")
        if initial_cash <= 0:
            raise ValueError("初始资金必须大于 0")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO simulation_accounts
                (name, initial_cash, cash_balance, start_date, current_date,
                 commission_rate, minimum_commission, sell_tax_rate, slippage_bps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name.strip(), initial_cash, initial_cash, start_date.isoformat(), start_date.isoformat(),
                 config.commission_rate, config.minimum_commission, config.sell_tax_rate, config.slippage_bps),
            )
            account_id = int(cursor.lastrowid)
        return self.get_account(account_id)

    def list_accounts(self) -> list[SimulationAccount]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM simulation_accounts ORDER BY id").fetchall()
        return [self._account(row) for row in rows]

    def get_account(self, account_id: int) -> SimulationAccount:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM simulation_accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise DatabaseError("模拟账户不存在")
        return self._account(row)

    def update_account_state(self, account_id: int, cash: float, current_date: date, realized_pnl: float) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE simulation_accounts SET cash_balance=?, current_date=?, realized_pnl=? WHERE id=?",
                (cash, current_date.isoformat(), realized_pnl, account_id),
            )

    def add_order(self, order: SimulationOrder) -> SimulationOrder:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO simulation_orders
                (account_id, stock_code, stock_name, side, quantity, submitted_date, status,
                 reason, planned_holding_period, stop_loss_condition, target_condition, confidence_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order.account_id, order.stock_code, order.stock_name, order.side, order.quantity,
                 order.submitted_date.isoformat(), order.status, order.reason, order.planned_holding_period,
                 order.stop_loss_condition, order.target_condition, order.confidence_level),
            )
            order_id = int(cursor.lastrowid)
        return self.get_order(order_id)

    def get_order(self, order_id: int) -> SimulationOrder:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM simulation_orders WHERE id=?", (order_id,)).fetchone()
        if row is None:
            raise DatabaseError("模拟订单不存在")
        return self._order(row)

    def list_orders(self, account_id: int, status: str | None = None) -> list[SimulationOrder]:
        sql = "SELECT * FROM simulation_orders WHERE account_id=?"
        params: tuple[object, ...] = (account_id,)
        if status:
            sql += " AND status=?"
            params += (status,)
        sql += " ORDER BY submitted_date, id"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._order(row) for row in rows]

    def set_order_result(self, order_id: int, status: str, execution_date: date | None = None,
                         fill_price: float | None = None, commission: float = 0, tax: float = 0,
                         rejection_reason: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE simulation_orders SET status=?, execution_date=?, fill_price=?,
                   commission=?, tax=?, rejection_reason=? WHERE id=?""",
                (status, execution_date.isoformat() if execution_date else None, fill_price,
                 commission, tax, rejection_reason, order_id),
            )

    def cancel_order(self, order_id: int, account_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE simulation_orders SET status='CANCELLED' WHERE id=? AND account_id=? AND status='PENDING'",
                (order_id, account_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("只有待处理订单可以取消")

    def upsert_snapshot(self, snapshot: SimulationSnapshot) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO simulation_daily_snapshots
                (account_id, snapshot_date, cash_balance, market_value, total_assets, unrealized_pnl,
                 realized_pnl, cumulative_return, daily_return, current_drawdown, max_drawdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, snapshot_date) DO UPDATE SET
                cash_balance=excluded.cash_balance, market_value=excluded.market_value,
                total_assets=excluded.total_assets, unrealized_pnl=excluded.unrealized_pnl,
                realized_pnl=excluded.realized_pnl, cumulative_return=excluded.cumulative_return,
                daily_return=excluded.daily_return, current_drawdown=excluded.current_drawdown,
                max_drawdown=excluded.max_drawdown""",
                (snapshot.account_id, snapshot.snapshot_date.isoformat(), snapshot.cash_balance,
                 snapshot.market_value, snapshot.total_assets, snapshot.unrealized_pnl,
                 snapshot.realized_pnl, snapshot.cumulative_return, snapshot.daily_return,
                 snapshot.current_drawdown, snapshot.max_drawdown),
            )

    def list_snapshots(self, account_id: int) -> list[SimulationSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM simulation_daily_snapshots WHERE account_id=? ORDER BY snapshot_date", (account_id,)
            ).fetchall()
        return [self._snapshot(row) for row in rows]

    @staticmethod
    def _account(row: sqlite3.Row) -> SimulationAccount:
        return SimulationAccount(
            int(row["id"]), str(row["name"]), float(row["initial_cash"]), float(row["cash_balance"]),
            date.fromisoformat(row["start_date"]), date.fromisoformat(row["current_date"]),
            float(row["commission_rate"]), float(row["minimum_commission"]),
            float(row["sell_tax_rate"]), float(row["slippage_bps"]), float(row["realized_pnl"]),
            datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _order(row: sqlite3.Row) -> SimulationOrder:
        return SimulationOrder(
            account_id=int(row["account_id"]), stock_code=str(row["stock_code"]),
            stock_name=str(row["stock_name"]), side=str(row["side"]), quantity=int(row["quantity"]),
            submitted_date=date.fromisoformat(row["submitted_date"]), status=str(row["status"]),
            reason=str(row["reason"]), planned_holding_period=str(row["planned_holding_period"]),
            stop_loss_condition=str(row["stop_loss_condition"]), target_condition=str(row["target_condition"]),
            confidence_level=int(row["confidence_level"]),
            execution_date=date.fromisoformat(row["execution_date"]) if row["execution_date"] else None,
            fill_price=float(row["fill_price"]) if row["fill_price"] is not None else None,
            commission=float(row["commission"]), tax=float(row["tax"]),
            rejection_reason=str(row["rejection_reason"]), id=int(row["id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> SimulationSnapshot:
        return SimulationSnapshot(
            account_id=int(row["account_id"]), snapshot_date=date.fromisoformat(row["snapshot_date"]),
            cash_balance=float(row["cash_balance"]), market_value=float(row["market_value"]),
            total_assets=float(row["total_assets"]), unrealized_pnl=float(row["unrealized_pnl"]),
            realized_pnl=float(row["realized_pnl"]), cumulative_return=float(row["cumulative_return"]),
            daily_return=float(row["daily_return"]), current_drawdown=float(row["current_drawdown"]),
            max_drawdown=float(row["max_drawdown"]), id=int(row["id"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
