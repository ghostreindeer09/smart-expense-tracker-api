"""Pydantic models for the Smart Expense Tracker API."""

from __future__ import annotations

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpenseCreate(BaseModel):
    """Payload for creating a new expense."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        json_schema_extra={
            "examples": [
                {
                    "title": "Lunch at Sweetgreen",
                    "amount": 14.75,
                    "category": "Food",
                    "date": "2026-07-31",
                }
            ]
        },
    )

    title: str = Field(
        ...,
        min_length=1,
        description="Short description of the expense.",
        examples=["Lunch at Sweetgreen"],
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Amount spent, a positive number (rounded to 2 decimal places).",
        examples=[14.75],
    )
    category: str = Field(
        ...,
        min_length=1,
        description="Category this expense belongs to.",
        examples=["Food"],
    )
    date: Date = Field(
        ...,
        description="When the expense happened, as an ISO 8601 date (YYYY-MM-DD).",
        examples=["2026-07-31"],
    )

    @field_validator("title", "category")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank or whitespace-only")
        return value

    @field_validator("amount")
    @classmethod
    def round_to_cents(cls, value: float) -> float:
        return round(value, 2)

    def build(self, expense_id: str) -> Expense:
        """Build a stored Expense with a server-generated id."""
        return Expense(id=expense_id, **self.model_dump())


class Expense(BaseModel):
    """A single recorded expense."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3f9a5b2e-8c1d-4e6f-9a0b-2c3d4e5f6071",
                    "title": "Lunch at Sweetgreen",
                    "amount": 14.75,
                    "category": "Food",
                    "date": "2026-07-31",
                }
            ]
        }
    )

    id: str = Field(description="Server-generated UUID identifying this expense.")
    title: str = Field(description="Short description of the expense.")
    amount: float = Field(description="Amount spent, rounded to 2 decimal places.")
    category: str = Field(description="Category this expense belongs to.")
    date: Date = Field(description="When the expense happened (ISO 8601 date).")


class TotalOut(BaseModel):
    """Total amount spent, optionally restricted to one category."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"total": 128.5}]})

    total: float = Field(description="Sum of matching expense amounts.")


class CategoryBreakdown(BaseModel):
    """Expense totals grouped by category."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"categories": {"Food": 45.0, "Transport": 12.0}}]}
    )

    categories: dict[str, float] = Field(
        description="Category name mapped to the sum of its expenses."
    )
