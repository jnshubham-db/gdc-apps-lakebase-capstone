"""FastAPI dependency providers.

Handlers declare what they need via ``Depends`` (through the ``Annotated``
aliases below) and never touch module globals or parse the raw request
themselves. This keeps handlers testable — any provider can be swapped with
``app.dependency_overrides`` in tests.
"""

from __future__ import annotations

from typing import Annotated

from databricks.sdk import WorkspaceClient
from fastapi import Depends, Query, Request
from psycopg import AsyncConnection

from .auth import actor_email, obo_client, sp_client
from .config import Settings, get_settings
from .db import lakebase_sp


async def get_db():
    """Yield a pooled Lakebase connection (SP identity). Sole caller of lakebase_sp()."""
    async with lakebase_sp() as conn:
        yield conn


def get_obo_client(request: Request) -> WorkspaceClient:
    """Calling user's client for warehouse/Genie. Only place Request is read."""
    return obo_client(request)


def get_actor_email(request: Request) -> str:
    """Calling user's email, for the audit trail."""
    return actor_email(request)


def get_sp_client() -> WorkspaceClient:
    return sp_client()


class PageParams:
    """Shared pagination params: page ≥ 1, page_size 1..100 (>100 → 422).

    ``after`` is an opaque keyset cursor: when present the list endpoint pages
    forward by keyset (index seek) instead of OFFSET; ``page`` is then just the
    echoed page number the client tracks for display.
    """

    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        after: str | None = Query(None),
    ):
        self.page = page
        self.page_size = page_size
        self.after = after
        self.offset = (page - 1) * page_size


class CustomerFilters:
    """Optional list filters, self-describing as a SQL WHERE clause."""

    def __init__(
        self,
        segment: str | None = Query(None),
        min_ltv: float | None = Query(None, ge=0),
        max_churn: float | None = Query(None, ge=0, le=1),
    ):
        self.segment = segment
        self.min_ltv = min_ltv
        self.max_churn = max_churn

    def where(self) -> tuple[str, dict[str, object]]:
        """Return ``(clause, params)`` — clause is '' or 'WHERE ...'."""
        conds, params = [], {}
        if self.segment:
            conds.append("segment_id = %(segment)s")
            params["segment"] = self.segment
        if self.min_ltv is not None:
            conds.append("lifetime_value >= %(min_ltv)s")
            params["min_ltv"] = self.min_ltv
        if self.max_churn is not None:
            conds.append("churn_score <= %(max_churn)s")
            params["max_churn"] = self.max_churn
        return (f"WHERE {' AND '.join(conds)}" if conds else ""), params


DbConn = Annotated[AsyncConnection, Depends(get_db)]
Obo = Annotated[WorkspaceClient, Depends(get_obo_client)]
Actor = Annotated[str, Depends(get_actor_email)]
Sp = Annotated[WorkspaceClient, Depends(get_sp_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Pagination = Annotated[PageParams, Depends(PageParams)]
Filters = Annotated[CustomerFilters, Depends(CustomerFilters)]
