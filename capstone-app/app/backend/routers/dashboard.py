"""Analytics dashboard + app-config endpoints (T4).

``/api/config`` exposes the static workspace ids the frontend needs (host +
dashboard + Genie space). ``/api/dashboard/analytics`` recomputes the five
provisioned AI/BI charts natively: four gold-table aggregates run on the SQL
warehouse via OBO (the calling rep's identity), fanned out and TTL-cached.

SQL lives in named constants below the handlers, mirroring the customers router.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import SettingsDep

router = APIRouter(prefix="/api", tags=["dashboard"])


class AppConfig(BaseModel):
    databricks_host: str
    dashboard_id: str | None = None
    genie_space_id: str | None = None


@router.get("/config", response_model=AppConfig)
async def get_config(settings: SettingsDep) -> AppConfig:
    return AppConfig(
        databricks_host=settings.databricks_host,
        dashboard_id=settings.dashboard_id,
        genie_space_id=settings.genie_space_id,
    )
