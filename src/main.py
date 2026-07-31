"""FastAPI application and routes for the Smart Expense Tracker API."""

from __future__ import annotations

import math
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .models import CategoryBreakdown, Expense, ExpenseCreate, TotalOut
from .storage import ExpenseRepository, JsonFileStorage

DEFAULT_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "expenses.json"


def _build_repository() -> ExpenseRepository:
    data_file = Path(os.environ.get("EXPENSE_DATA_FILE", str(DEFAULT_DATA_FILE)))
    return ExpenseRepository(JsonFileStorage(data_file))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repository = _build_repository()
    yield


app = FastAPI(
    title="Smart Expense Tracker API",
    summary="Track personal expenses with no database required.",
    description=(
        "A small API for recording expenses. Data lives in memory and is "
        "persisted to a local JSON file, so a restart does not lose anything. "
        "Amounts are positive floats (rounded to 2 decimal places); category "
        "filters are case-insensitive."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI's standard 422 shape, safe to serialize.

    The default handler crashes with a 500 when the offending input contains a
    non-finite float (e.g. JSON ``Infinity``/``NaN``), because those values
    cannot be serialized back into the error response. We render them as
    strings instead.
    """
    errors = exc.errors()
    for error in errors:
        value = error.get("input")
        if isinstance(value, float) and not math.isfinite(value):
            error["input"] = repr(value)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(errors)},
    )


def get_repository() -> ExpenseRepository:
    return app.state.repository


RepoDep = Annotated[ExpenseRepository, Depends(get_repository)]


@app.post(
    "/expenses",
    response_model=Expense,
    status_code=status.HTTP_201_CREATED,
    summary="Add an expense",
    description=(
        "Creates an expense with a server-generated UUID id and returns the "
        "stored record. Returns 422 with details when the payload is invalid "
        "(missing fields, non-positive amount, malformed date, blank title/category)."
    ),
    tags=["expenses"],
)
def create_expense(payload: ExpenseCreate, repo: RepoDep) -> Expense:
    return repo.add(payload.build(str(uuid.uuid4())))


@app.get(
    "/expenses",
    response_model=list[Expense],
    summary="List expenses",
    description=(
        "Returns all expenses, newest by date first. Pass ?category=<name> to "
        "filter by category (case-insensitive)."
    ),
    tags=["expenses"],
)
def list_expenses(
    repo: RepoDep,
    category: Annotated[
        str | None, Query(description="Only return expenses in this category (case-insensitive).")
    ] = None,
) -> list[Expense]:
    return repo.list(category=category)


@app.get(
    "/expenses/total",
    response_model=TotalOut,
    summary="Total of expenses",
    description=(
        "Sum of all expense amounts. Pass ?category=<name> to total a single "
        "category (case-insensitive). Returns 0 when there are no matching expenses."
    ),
    tags=["expenses"],
)
def total_expenses(
    repo: RepoDep,
    category: Annotated[
        str | None, Query(description="Only total expenses in this category (case-insensitive).")
    ] = None,
) -> TotalOut:
    return TotalOut(total=repo.total(category=category))


@app.get(
    "/expenses/total/by-category",
    response_model=CategoryBreakdown,
    summary="Expense totals by category",
    description=(
        "Sums expense amounts grouped by category. Grouping is case-insensitive "
        "(the display name comes from the first expense seen for that category). "
        "Returns an empty object when there are no expenses."
    ),
    tags=["expenses"],
)
def total_by_category(repo: RepoDep) -> CategoryBreakdown:
    return CategoryBreakdown(categories=repo.total_by_category())


@app.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an expense",
    description=(
        "Removes the expense with the given id and returns 204. Returns 404 if "
        "no expense with that id exists."
    ),
    tags=["expenses"],
)
def delete_expense(expense_id: str, repo: RepoDep) -> Response:
    if not repo.delete(expense_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No expense found with id '{expense_id}'.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
