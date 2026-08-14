"""FastAPI application entrypoint (T3).

Wires middleware (gzip, request-id), the customers router, the SPA static
mount, and a lifespan that creates the pagination index at startup and closes
the Lakebase pool at shutdown.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .db import close_pool, lakebase_sp
from .routers import customers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Composite index backing the default list sort/filter. Idempotent, and
# recreated on startup so a full re-sync of the synced table can't leave it
# missing (indexes/reads/DROP are permitted on synced tables).
_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_customers_seg_ltv "
    "ON customers_synced (segment_id, lifetime_value DESC)"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with lakebase_sp() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_INDEX_DDL)
            await conn.commit()
        log.info("startup: pagination index ensured")
    except Exception:
        log.warning("startup: could not ensure pagination index", exc_info=True)
    yield
    await close_pool()


app = FastAPI(title="Customer 360", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


app.include_router(customers.router)

if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
