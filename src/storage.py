"""Storage layer: an in-memory dict of expenses with optional JSON file persistence.

The single point of truth is an in-memory ``dict`` held by
:class:`ExpenseRepository`. Every mutation is pushed to a :class:`Storage`
backend. Two backends ship here:

* :class:`MemoryStorage`  - nothing is written to disk (used in tests).
* :class:`JsonFileStorage` - the full dataset is loaded into memory once at
  startup and written back to disk after every mutation.

JSON file writes are atomic: the data is written to a temp file in the same
directory and then moved over the real file with ``os.replace``, so a crash
mid-write can never leave a half-written JSON file.
"""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from .models import Expense


class Storage(ABC):
    """Interface for where expense data lives and how it is persisted."""

    @abstractmethod
    def load(self) -> dict[str, Expense]:
        """Return all expenses keyed by their id."""

    @abstractmethod
    def save(self, expenses: dict[str, Expense]) -> None:
        """Persist the given expenses. Called after every mutation."""


class MemoryStorage(Storage):
    """Pure in-memory backend; nothing is ever written to disk."""

    def load(self) -> dict[str, Expense]:
        return {}

    def save(self, expenses: dict[str, Expense]) -> None:
        pass


class JsonFileStorage(Storage):
    """In-memory dict backed by a local JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, Expense]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Corrupt expense data file {self._path}: {exc}") from exc
        if not isinstance(raw, list):
            raise RuntimeError(
                f"Unexpected shape in {self._path}: expected a JSON list of expenses"
            )
        expenses: dict[str, Expense] = {}
        for item in raw:
            expense = Expense.model_validate(item)
            expenses[expense.id] = expense
        return expenses

    def save(self, expenses: dict[str, Expense]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [expense.model_dump(mode="json") for expense in expenses.values()]
        temp = self._path.with_name(self._path.name + ".tmp")
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self._path)


class ExpenseRepository:
    """The single point of truth for expense data.

    Holds the in-memory dict and pushes every mutation through to the backing
    :class:`Storage`. Reads take a lock so concurrent requests are safe.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._expenses: dict[str, Expense] = storage.load()
        self._lock = threading.RLock()

    def add(self, expense: Expense) -> Expense:
        with self._lock:
            self._expenses[expense.id] = expense
            self._storage.save(self._expenses)
        return expense

    def list(self, category: str | None = None) -> list[Expense]:
        """All expenses, newest by date first. Filters case-insensitively."""
        with self._lock:
            expenses = list(self._expenses.values())
        if category is not None:
            needle = category.casefold()
            expenses = [e for e in expenses if e.category.casefold() == needle]
        expenses.sort(key=lambda e: e.date, reverse=True)
        return expenses

    def total(self, category: str | None = None) -> float:
        """Sum of matching amounts, rounded to 2 decimal places."""
        return round(sum(expense.amount for expense in self.list(category)), 2)

    def total_by_category(self) -> dict[str, float]:
        """Totals grouped by category (case-insensitive).

        The display name shown for a group is the casing of the first expense
        seen for that category. Returns an empty dict when there are no expenses.
        """
        with self._lock:
            expenses = list(self._expenses.values())
        totals: dict[str, float] = {}
        display_names: dict[str, str] = {}
        for expense in expenses:
            key = expense.category.casefold()
            display_names.setdefault(key, expense.category)
            totals[key] = round(totals.get(key, 0.0) + expense.amount, 2)
        return {display_names[key]: total for key, total in totals.items()}

    def delete(self, expense_id: str) -> bool:
        """Delete an expense by id. Returns False if it did not exist."""
        with self._lock:
            if expense_id not in self._expenses:
                return False
            del self._expenses[expense_id]
            self._storage.save(self._expenses)
            return True
