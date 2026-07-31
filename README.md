# Smart Expense Tracker API

A small FastAPI service for recording personal expenses. It validates input with
Pydantic v2, keeps everything in memory, and optionally persists to a local JSON
file so data survives a restart. No database required.

## Features

- `POST /expenses` — add an expense (server-generated UUID, validated payload).
- `GET /expenses` — list all expenses, newest by date first.
- `GET /expenses?category=Food` — filter by category (case-insensitive).
- `GET /expenses/total` — total of all expenses (and `?category=...` for one category).
- `GET /expenses/total/by-category` — totals grouped by category.
- `DELETE /expenses/{id}` — delete an expense (404 if it does not exist).
- Interactive OpenAPI/Swagger docs at `/docs` with schemas and examples for every endpoint.

Amounts are positive floats rounded to 2 decimal places; empty totals return `0.0`.

## Requirements

- Python 3.11+

## Setup (from a clean checkout)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the server

```bash
uvicorn src.main:app --reload
```

The API is served at `http://127.0.0.1:8000`. Interactive docs:
`http://127.0.0.1:8000/docs`.

## Run the tests

```bash
pytest -q
```

## Example requests

```bash
# Add an expense
curl -s -X POST http://127.0.0.1:8000/expenses \
  -H 'Content-Type: application/json' \
  -d '{"title": "Lunch at Sweetgreen", "amount": 14.75, "category": "Food", "date": "2026-07-31"}'

# List all expenses (newest first)
curl -s http://127.0.0.1:8000/expenses

# List only Food expenses (case-insensitive)
curl -s "http://127.0.0.1:8000/expenses?category=FOOD"

# Total of all expenses
curl -s http://127.0.0.1:8000/expenses/total

# Total for one category
curl -s "http://127.0.0.1:8000/expenses/total?category=Food"

# Totals grouped by category
curl -s http://127.0.0.1:8000/expenses/total/by-category

# Delete an expense (replace <id> with the id from a create response)
curl -s -X DELETE http://127.0.0.1:8000/expenses/<id>
```

## Storage

Data lives in memory (a `dict` keyed by expense id) and is mirrored to
`data/expenses.json` at the project root: loaded once on startup, rewritten
after every mutation. Writes are atomic (temp file + `os.replace`), and
requests are serialized through a lock. To point at a different file, set the
`EXPENSE_DATA_FILE` environment variable.

This is intentionally simple — it is not a database, and the full-file rewrite
is O(n) per write, which is fine at this scale.
