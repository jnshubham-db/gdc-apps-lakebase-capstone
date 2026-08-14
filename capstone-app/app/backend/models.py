"""Data + API models (SQLModel).

Each ``table=True`` class is *both* the Pydantic model (API shape,
OpenAPI-documented) and the table definition — a single source of truth for
the schema. Field names/types mirror the live Lakebase columns; queries still
run through the async psycopg pool (see ``db.py``), so these classes are used
to *validate rows into typed objects*, not to drive an SQLAlchemy engine.

API-only (non-table) models cover request bodies, the paginated envelope, and
the warehouse-computed metrics that have no backing table.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlmodel import JSON, Column, Field, SQLModel

# --- persisted tables -------------------------------------------------------


class CustomerSynced(SQLModel, table=True):
    __tablename__ = "customers_synced"

    customer_id: str = Field(primary_key=True)
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    country: str | None = None
    city: str | None = None
    age: int | None = None
    gender: str | None = None
    signup_date: dt.date | None = None
    segment_id: str | None = None
    lifetime_value: float | None = None
    last_purchase_date: dt.date | None = None
    churn_score: float | None = None
    phone: str | None = None
    updated_at: dt.datetime | None = None


class TransactionSynced(SQLModel, table=True):
    __tablename__ = "transactions_synced"

    transaction_id: str = Field(primary_key=True)
    customer_id: str
    product_id: str | None = None
    transaction_date: dt.date | None = None
    channel: str | None = None
    status: str | None = None
    amount: float | None = None


class CustomerNote(SQLModel, table=True):
    __tablename__ = "customer_notes_staging"

    note_id: uuid.UUID | None = Field(default=None, primary_key=True)
    customer_id: str
    author_email: str
    note_text: str
    created_at: dt.datetime | None = None
    processed: bool = False
    processed_at: dt.datetime | None = None


class SegmentOverride(SQLModel, table=True):
    __tablename__ = "customer_segment_overrides_staging"

    override_id: uuid.UUID | None = Field(default=None, primary_key=True)
    customer_id: str
    override_segment: str
    reason: str | None = None
    author_email: str
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    processed: bool = False
    processed_at: dt.datetime | None = None


class AuditLog(SQLModel, table=True):
    __tablename__ = "customer_audit_log"

    audit_id: int | None = Field(default=None, primary_key=True)
    customer_id: str
    action: str
    actor_email: str
    payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: dt.datetime | None = None


# --- API request bodies -----------------------------------------------------


class NoteIn(BaseModel):
    note_text: str


class SegmentOverrideIn(BaseModel):
    override_segment: str
    reason: str | None = None


# --- API response composites ------------------------------------------------


class CustomerDetail(BaseModel):
    """Profile + recent activity, returned by GET /customers/{id}."""

    profile: CustomerSynced
    transactions: list[TransactionSynced]


class CategorySpend(BaseModel):
    category: str
    amount: float


class CustomerMetrics(BaseModel):
    """Warehouse-computed aggregates (no backing table)."""

    customer_id: str
    segment_name: str | None = None
    lifetime_spend: float
    top_categories: list[CategorySpend]
    spend_30d: float
    spend_90d: float
    open_tickets: int
    avg_csat: float | None = None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --- forward-ETL job runs (T7) ----------------------------------------------


class RunTrigger(BaseModel):
    run_id: int


class RunSummary(BaseModel):
    run_id: int
    state: str
    result_state: str | None = None
    start_time: int | None = None
    duration_ms: int | None = None


class RunStatus(RunSummary):
    run_page_url: str | None = None
