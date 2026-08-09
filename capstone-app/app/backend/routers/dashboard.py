"""Analytics dashboard + app-config endpoints (T4).

``/api/config`` exposes the static workspace ids the frontend needs (host +
dashboard + Genie space). ``/api/dashboard/analytics`` recomputes the five
provisioned AI/BI charts natively: four gold-table aggregates run on the SQL
warehouse via OBO (the calling rep's identity), fanned out and TTL-cached.

SQL lives in named constants below the handlers, mirroring the customers router.
"""

from __future__ import annotations

import asyncio

from cachetools import TTLCache
from databricks.sdk import WorkspaceClient
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..deps import Obo, SettingsDep

router = APIRouter(prefix="/api", tags=["dashboard"])


class AppConfig(BaseModel):
    databricks_host: str
    dashboard_id: str | None = None
    genie_space_id: str | None = None


class SegmentAgg(BaseModel):
    segment_name: str
    customers: int
    avg_ltv: float
    avg_churn: float


class ProductRevenue(BaseModel):
    product_name: str
    category: str
    revenue: float
    units: int


class TicketPoint(BaseModel):
    week: str
    category: str
    tickets: int


class ChurnBucket(BaseModel):
    bucket: float
    customers: int


class DashboardAnalytics(BaseModel):
    segments: list[SegmentAgg]
    products: list[ProductRevenue]
    tickets: list[TicketPoint]
    churn_buckets: list[ChurnBucket]


# Slow-changing org-wide analytics — cache the whole payload for 5 min.
_analytics_cache: TTLCache = TTLCache(maxsize=1, ttl=300)


@router.get("/config", response_model=AppConfig)
async def get_config(settings: SettingsDep) -> AppConfig:
    return AppConfig(
        databricks_host=settings.databricks_host,
        dashboard_id=settings.dashboard_id,
        genie_space_id=settings.genie_space_id,
    )


def _run_sql(w: WorkspaceClient, sql: str) -> list[dict]:
    """Run one param-less warehouse statement, return rows as dicts."""
    s = get_settings()
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=s.warehouse_id,
        catalog=s.capstone_catalog,
        schema=s.capstone_schema,
        wait_timeout="30s",
    )
    cols = [c.name for c in (resp.manifest.schema.columns or [])]
    data = resp.result.data_array if resp.result and resp.result.data_array else []
    return [dict(zip(cols, row)) for row in data]


@router.get("/dashboard/analytics", response_model=DashboardAnalytics)
async def dashboard_analytics(obo: Obo) -> DashboardAnalytics:
    if "payload" in _analytics_cache:
        return _analytics_cache["payload"]

    segments, products, tickets, churn = await asyncio.gather(
        asyncio.to_thread(_run_sql, obo, _Q_SEGMENTS),
        asyncio.to_thread(_run_sql, obo, _Q_PRODUCTS),
        asyncio.to_thread(_run_sql, obo, _Q_TICKETS),
        asyncio.to_thread(_run_sql, obo, _Q_CHURN),
    )

    payload = DashboardAnalytics(
        segments=[
            SegmentAgg(
                segment_name=r["segment_name"],
                customers=int(r["customers"]),
                avg_ltv=float(r["avg_ltv"]),
                avg_churn=float(r["avg_churn"]),
            )
            for r in segments
        ],
        products=[
            ProductRevenue(
                product_name=r["product_name"],
                category=r["category"],
                revenue=float(r["revenue"]),
                units=int(r["units"]),
            )
            for r in products
        ],
        tickets=[
            TicketPoint(week=str(r["week"]), category=r["category"], tickets=int(r["tickets"]))
            for r in tickets
        ],
        churn_buckets=[
            ChurnBucket(bucket=float(r["bucket"]), customers=int(r["customers"])) for r in churn
        ],
    )
    _analytics_cache["payload"] = payload
    return payload


_Q_SEGMENTS = (
    "SELECT s.segment_name, COUNT(*) AS customers, "
    "ROUND(AVG(c.lifetime_value), 2) AS avg_ltv, "
    "ROUND(AVG(c.churn_score), 3) AS avg_churn "
    "FROM customers c JOIN customer_segments s ON c.segment_id = s.segment_id "
    "GROUP BY s.segment_name ORDER BY avg_ltv DESC"
)

_Q_PRODUCTS = (
    "SELECT p.name AS product_name, p.category, "
    "ROUND(SUM(t.amount), 2) AS revenue, COUNT(*) AS units "
    "FROM transactions t JOIN products p ON t.product_id = p.product_id "
    "WHERE t.status = 'completed' "
    "GROUP BY p.name, p.category ORDER BY revenue DESC LIMIT 15"
)

_Q_TICKETS = (
    "SELECT DATE_TRUNC('week', opened_at) AS week, category, COUNT(*) AS tickets "
    "FROM support_tickets "
    "GROUP BY DATE_TRUNC('week', opened_at), category ORDER BY week"
)

_Q_CHURN = (
    "SELECT ROUND(FLOOR(churn_score * 10) / 10, 1) AS bucket, COUNT(*) AS customers "
    "FROM customers "
    "GROUP BY ROUND(FLOOR(churn_score * 10) / 10, 1) ORDER BY bucket"
)
