"""Validated transaction CRUD orchestration."""

from __future__ import annotations

from database.db import TransactionRepository
from database.models import Transaction
from services.portfolio_service import calculate_positions


class TransactionService:
    def __init__(self, repository: TransactionRepository) -> None:
        self.repository = repository

    def list_all(self) -> list[Transaction]:
        return self.repository.list_all()

    def add(self, transaction: Transaction) -> Transaction:
        calculate_positions([*self.list_all(), transaction], include_closed=True)
        return self.repository.add(transaction)

    def update(self, transaction: Transaction) -> Transaction:
        if transaction.id is None:
            raise ValueError("缺少交易 ID")
        proposed = [item for item in self.list_all() if item.id != transaction.id]
        proposed.append(transaction)
        calculate_positions(proposed, include_closed=True)
        return self.repository.update(transaction)

    def delete(self, transaction_id: int) -> None:
        proposed = [item for item in self.list_all() if item.id != transaction_id]
        calculate_positions(proposed, include_closed=True)
        self.repository.delete(transaction_id)
