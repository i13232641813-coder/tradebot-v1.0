"""SQLite CRUD persistence tests."""

from datetime import date

from database.db import TransactionRepository
from database.models import Transaction


def test_transaction_crud_persists_across_repository_instances(tmp_path) -> None:
    path = tmp_path / "persist.db"
    repository = TransactionRepository(path)
    created = repository.add(Transaction("AAPL", "Apple", "BUY", 100, 10, date(2026, 1, 2)))
    assert created.id is not None
    reopened = TransactionRepository(path)
    assert reopened.get(created.id).stock_name == "Apple"
    updated = Transaction(**{**created.__dict__, "note": "updated"})
    reopened.update(updated)
    assert repository.get(created.id).note == "updated"
    repository.delete(created.id)
    assert reopened.list_all() == []
