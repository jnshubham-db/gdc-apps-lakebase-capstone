"""Customer read/write endpoints (T3).

Reads and writes go to Lakebase as the SP (injected ``DbConn``); the metrics
endpoint is the one warehouse+OBO path (injected ``Obo``), computing
cross-table aggregates over gold that aren't synced to Lakebase.

SQL lives in named constants below the handlers so the handlers read as
intent, not string-building.
"""

from __future__ import annotations

import asyncio
import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem
from fastapi import APIRouter, HTTPException
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..config import get_settings
from ..deps import Actor, DbConn, Filters, Obo, Pagination
from ..models import (
    CategorySpend,
    CustomerDetail,
    CustomerMetrics,
    CustomerSynced,
    NoteIn,
    Page,
    SegmentOverrideIn,
    TransactionSynced,
)

router = APIRouter(prefix="/api/customers", tags=["customers"])


# --- small query helpers ----------------------------------------------------


async def _rows(conn: AsyncConnection, sql: str, params=None) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


async def _row(conn: AsyncConnection, sql: str, params=None) -> dict | None:
    rows = await _rows(conn, sql, params)
    return rows[0] if rows else None


# --- reads (Lakebase, SP) ---------------------------------------------------


@router.get("", response_model=Page[CustomerSynced])
async def list_customers(conn: DbConn, page: Pagination, filters: Filters) -> Page[CustomerSynced]:
    clause, params = filters.where()
    total = (await _row(conn, f"SELECT COUNT(*) AS n FROM customers_synced {clause}", params))["n"]
    rows = await _rows(
        conn,
        f"{_LIST_SELECT} {clause} {_LIST_ORDER} LIMIT %(limit)s OFFSET %(offset)s",
        {**params, "limit": page.page_size, "offset": page.offset},
    )
    items = [CustomerSynced.model_validate(r) for r in rows]
    return Page(items=items, total=total, page=page.page, page_size=page.page_size)


@router.get("/{customer_id}", response_model=CustomerDetail)
async def get_customer(customer_id: str, conn: DbConn) -> CustomerDetail:
    profile = await _row(conn, _CUSTOMER_BY_ID, (customer_id,))
    if profile is None:
        raise HTTPException(status_code=404, detail="customer not found")
    txns = await _rows(conn, _RECENT_TXNS, (customer_id,))
    return CustomerDetail(
        profile=CustomerSynced.model_validate(profile),
        transactions=[TransactionSynced.model_validate(t) for t in txns],
    )


# --- metrics (warehouse + OBO) ----------------------------------------------


def _run_stmt(w: WorkspaceClient, sql: str, customer_id: str) -> list[dict]:
    """Run one warehouse statement bound to :cid, return rows as dicts."""
    s = get_settings()
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=s.warehouse_id,
        catalog=s.capstone_catalog,
        schema=s.capstone_schema,
        parameters=[StatementParameterListItem(name="cid", value=customer_id)],
        wait_timeout="30s",
    )
    cols = [c.name for c in (resp.manifest.schema.columns or [])]
    data = resp.result.data_array if resp.result and resp.result.data_array else []
    return [dict(zip(cols, row)) for row in data]


@router.get("/{customer_id}/metrics", response_model=CustomerMetrics)
async def customer_metrics(customer_id: str, obo: Obo) -> CustomerMetrics:
    agg, cats, tickets, seg = await asyncio.gather(
        asyncio.to_thread(_run_stmt, obo, _M_SPEND, customer_id),
        asyncio.to_thread(_run_stmt, obo, _M_CATEGORIES, customer_id),
        asyncio.to_thread(_run_stmt, obo, _M_TICKETS, customer_id),
        asyncio.to_thread(_run_stmt, obo, _M_SEGMENT, customer_id),
    )
    if not seg:
        raise HTTPException(status_code=404, detail="customer not found")

    a = agg[0] if agg else {}
    t = tickets[0] if tickets else {}
    return CustomerMetrics(
        customer_id=customer_id,
        segment_name=seg[0].get("segment_name"),
        lifetime_spend=float(a.get("lifetime") or 0),
        spend_30d=float(a.get("d30") or 0),
        spend_90d=float(a.get("d90") or 0),
        top_categories=[
            CategorySpend(category=c["category"], amount=float(c["amount"])) for c in cats
        ],
        open_tickets=int(t.get("open_tickets") or 0),
        avg_csat=float(t["avg_csat"]) if t.get("avg_csat") is not None else None,
    )


# --- writes (transactional + audited, SP) -----------------------------------


async def _audit(conn: AsyncConnection, customer_id: str, action: str, actor: str, payload: dict):
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO customer_audit_log (customer_id, action, actor_email, payload) "
            "VALUES (%s, %s, %s, %s)",
            (customer_id, action, actor, json.dumps(payload)),
        )


@router.post("/{customer_id}/notes", status_code=201)
async def add_note(customer_id: str, body: NoteIn, conn: DbConn, actor: Actor) -> dict:
    note = await _row(conn, _INSERT_NOTE, (customer_id, actor, body.note_text))
    await _audit(conn, customer_id, "add_note", actor, {"note_id": str(note["note_id"])})
    await conn.commit()
    return {"note_id": str(note["note_id"]), "created_at": note["created_at"].isoformat()}


@router.post("/{customer_id}/segment")
async def override_segment(
    customer_id: str, body: SegmentOverrideIn, conn: DbConn, actor: Actor
) -> dict:
    ov = await _row(
        conn, _UPSERT_OVERRIDE, (customer_id, body.override_segment, body.reason, actor)
    )
    await _audit(
        conn, customer_id, "override_segment", actor, {"override_segment": body.override_segment}
    )
    await conn.commit()
    return {"override_id": str(ov["override_id"]), "override_segment": body.override_segment}


# --- SQL --------------------------------------------------------------------

_LIST_SELECT = "SELECT * FROM customers_synced"
_LIST_ORDER = "ORDER BY lifetime_value DESC NULLS LAST, customer_id"
_CUSTOMER_BY_ID = "SELECT * FROM customers_synced WHERE customer_id = %s"
_RECENT_TXNS = (
    "SELECT * FROM transactions_synced WHERE customer_id = %s "
    "ORDER BY transaction_date DESC LIMIT 20"
)

_INSERT_NOTE = (
    "INSERT INTO customer_notes_staging (customer_id, author_email, note_text) "
    "VALUES (%s, %s, %s) RETURNING note_id, created_at"
)
_UPSERT_OVERRIDE = (
    "INSERT INTO customer_segment_overrides_staging "
    "(customer_id, override_segment, reason, author_email) VALUES (%s, %s, %s, %s) "
    "ON CONFLICT (customer_id) DO UPDATE SET "
    "override_segment = EXCLUDED.override_segment, reason = EXCLUDED.reason, "
    "author_email = EXCLUDED.author_email, updated_at = NOW(), processed = FALSE "
    "RETURNING override_id"
)

# Metrics run against gold via the warehouse (:cid bound parameter).
_M_SPEND = (
    "SELECT COALESCE(SUM(amount), 0) AS lifetime, "
    "COALESCE(SUM(CASE WHEN transaction_date >= current_date - INTERVAL 30 DAYS THEN amount END), 0) AS d30, "
    "COALESCE(SUM(CASE WHEN transaction_date >= current_date - INTERVAL 90 DAYS THEN amount END), 0) AS d90 "
    "FROM transactions WHERE customer_id = :cid AND status = 'completed'"
)
_M_CATEGORIES = (
    "SELECT p.category AS category, SUM(t.amount) AS amount "
    "FROM transactions t JOIN products p ON t.product_id = p.product_id "
    "WHERE t.customer_id = :cid AND t.status = 'completed' "
    "GROUP BY p.category ORDER BY amount DESC LIMIT 5"
)
_M_TICKETS = (
    "SELECT COUNT_IF(status <> 'closed') AS open_tickets, AVG(csat_score) AS avg_csat "
    "FROM support_tickets WHERE customer_id = :cid"
)
_M_SEGMENT = (
    "SELECT s.segment_name AS segment_name FROM customers c "
    "JOIN customer_segments s ON c.segment_id = s.segment_id WHERE c.customer_id = :cid"
)
