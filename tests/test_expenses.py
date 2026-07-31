"""Test suite for the Smart Expense Tracker API.

Runs against FastAPI's TestClient with a MemoryStorage-backed repository,
so no server is started and nothing is written to disk.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import app, get_repository
from src.storage import ExpenseRepository, MemoryStorage


def expense_payload(**overrides):
    payload = {
        "title": "Lunch at Sweetgreen",
        "amount": 14.75,
        "category": "Food",
        "date": "2026-07-31",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client():
    repo = ExpenseRepository(MemoryStorage())
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add_expense(client, **overrides) -> dict:
    """POST an expense and assert it was created; returns the stored record."""
    resp = client.post("/expenses", json=expense_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# POST /expenses — happy path
# --------------------------------------------------------------------------


def test_create_expense_success(client):
    resp = client.post(
        "/expenses",
        json=expense_payload(title="Groceries", amount=42.5, category="Food", date="2026-07-30"),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Groceries"
    assert body["amount"] == 42.5
    assert body["category"] == "Food"
    assert body["date"] == "2026-07-30"
    assert uuid.UUID(body["id"])  # server-generated UUID


def test_create_expense_trims_whitespace(client):
    body = add_expense(client, title="  Coffee  ", category="  Food  ")
    assert body["title"] == "Coffee"
    assert body["category"] == "Food"


def test_create_expense_rounds_amount_to_two_decimals(client):
    body = add_expense(client, amount=14.756)
    assert body["amount"] == 14.76


# --------------------------------------------------------------------------
# POST /expenses — validation failures (422)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},  # all fields missing
        {"amount": 10.0, "category": "Food", "date": "2026-07-31"},  # missing title
        {"title": "", "amount": 10.0, "category": "Food", "date": "2026-07-31"},  # empty title
        {"title": "   ", "amount": 10.0, "category": "Food", "date": "2026-07-31"},  # whitespace title
        {"title": "Lunch", "category": "Food", "date": "2026-07-31"},  # missing amount
        {"title": "Lunch", "amount": 0, "category": "Food", "date": "2026-07-31"},  # zero amount
        {"title": "Lunch", "amount": -5, "category": "Food", "date": "2026-07-31"},  # negative amount
        {"title": "Lunch", "amount": "abc", "category": "Food", "date": "2026-07-31"},  # non-numeric
        {"title": "Lunch", "amount": 5.0, "date": "2026-07-31"},  # missing category
        {"title": "Lunch", "amount": 5.0, "category": " ", "date": "2026-07-31"},  # blank category
        {"title": "Lunch", "amount": 5.0, "category": "Food"},  # missing date
        {"title": "Lunch", "amount": 5.0, "category": "Food", "date": "not-a-date"},
        {"title": "Lunch", "amount": 5.0, "category": "Food", "date": "2026-13-01"},  # bad month
        {"title": "Lunch", "amount": 5.0, "category": "Food", "date": "2026-02-30"},  # impossible day
        {"title": "Lunch", "amount": 5.0, "category": "Food", "date": "31-07-2026"},  # wrong format
    ],
)
def test_create_expense_rejects_bad_input(client, payload):
    resp = client.post("/expenses", json=payload)
    assert resp.status_code == 422
    assert "detail" in resp.json()


@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN"])
def test_create_expense_rejects_non_finite_amount(client, value):
    # httpx refuses to encode non-finite floats as JSON, so send a raw body.
    raw = (
        '{"title": "Lunch", "amount": %s, "category": "Food", "date": "2026-07-31"}'
        % value
    )
    resp = client.post(
        "/expenses",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "finite" in detail[0]["msg"]
    assert detail[0]["input"] in ("inf", "-inf", "nan")


def test_create_expense_error_identifies_missing_field(client):
    resp = client.post(
        "/expenses",
        json={"amount": 10.0, "category": "Food", "date": "2026-07-31"},  # no title
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"][0]["msg"] == "Field required"
    assert "title" in body["detail"][0]["loc"]


# --------------------------------------------------------------------------
# GET /expenses — list
# --------------------------------------------------------------------------


def test_list_expenses_empty(client):
    resp = client.get("/expenses")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_expenses_newest_first(client):
    add_expense(client, title="Oldest", date="2026-07-01")
    add_expense(client, title="Middle", date="2026-07-15")
    add_expense(client, title="Newest", date="2026-07-31")
    titles = [e["title"] for e in client.get("/expenses").json()]
    assert titles == ["Newest", "Middle", "Oldest"]


def test_list_expenses_filter_by_category_case_insensitive(client):
    add_expense(client, title="Lunch", category="Food")
    add_expense(client, title="Coffee", category="food")
    add_expense(client, title="Bus", category="Transport")
    for query in ("Food", "food", "FOOD"):
        titles = [e["title"] for e in client.get(f"/expenses?category={query}").json()]
        assert sorted(titles) == ["Coffee", "Lunch"]


def test_list_expenses_filter_no_match_returns_empty(client):
    add_expense(client, category="Food")
    assert client.get("/expenses?category=Entertainment").json() == []
    assert client.get("/expenses?category=").json() == []


# --------------------------------------------------------------------------
# GET /expenses/total
# --------------------------------------------------------------------------


def test_total_empty(client):
    resp = client.get("/expenses/total")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0.0}


def test_total_sums_all_expenses(client):
    add_expense(client, title="A", amount=0.1)
    add_expense(client, title="B", amount=0.2)
    add_expense(client, title="C", amount=10.0)
    assert client.get("/expenses/total").json() == {"total": 10.3}


def test_total_with_category(client):
    add_expense(client, title="Lunch", amount=5.0, category="Food")
    add_expense(client, title="Coffee", amount=3.5, category="food")
    add_expense(client, title="Bus", amount=2.0, category="Transport")
    assert client.get("/expenses/total?category=FOOD").json() == {"total": 8.5}


def test_total_with_category_no_match_returns_zero(client):
    add_expense(client, amount=5.0, category="Food")
    assert client.get("/expenses/total?category=Games").json() == {"total": 0.0}


# --------------------------------------------------------------------------
# GET /expenses/total/by-category
# --------------------------------------------------------------------------


def test_total_by_category_empty(client):
    resp = client.get("/expenses/total/by-category")
    assert resp.status_code == 200
    assert resp.json() == {"categories": {}}


def test_total_by_category_groups_case_insensitively(client):
    add_expense(client, title="Lunch", amount=10.0, category="Food")
    add_expense(client, title="Coffee", amount=5.0, category="food")
    add_expense(client, title="Bus", amount=20.0, category="Transport")
    body = client.get("/expenses/total/by-category").json()
    assert body == {"categories": {"Food": 15.0, "Transport": 20.0}}


# --------------------------------------------------------------------------
# DELETE /expenses/{id}
# --------------------------------------------------------------------------


def test_delete_expense_then_verify_gone(client):
    created = add_expense(client)
    expense_id = created["id"]

    resp = client.delete(f"/expenses/{expense_id}")
    assert resp.status_code == 204
    assert resp.content == b""

    remaining = client.get("/expenses").json()
    assert all(expense["id"] != expense_id for expense in remaining)

    # Deleting again confirms it is gone.
    assert client.delete(f"/expenses/{expense_id}").status_code == 404


def test_delete_expense_keeps_other_expenses(client):
    created = add_expense(client)
    add_expense(client, title="Another")
    assert client.delete(f"/expenses/{created['id']}").status_code == 204
    assert len(client.get("/expenses").json()) == 1


def test_delete_missing_expense_returns_404(client):
    resp = client.delete(f"/expenses/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert "no expense found" in resp.json()["detail"].lower()
