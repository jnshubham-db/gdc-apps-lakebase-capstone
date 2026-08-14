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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import close_pool, lakebase_sp
from .routers import customers, dashboard, genie, jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Indexes backing the list sort/filter. Idempotent, and recreated on startup so
# a full re-sync of the synced table can't leave them missing (indexes/reads/
# DROP are permitted on synced tables).
#   - idx_customers_seg_ltv: WHERE segment_id = ? ORDER BY lifetime_value DESC
#   - idx_customers_ltv_id:  the unfiltered keyset seek (lifetime_value, id)
_INDEX_DDL = (
    (
        "CREATE INDEX IF NOT EXISTS idx_customers_seg_ltv "
        "ON customers_synced (segment_id, lifetime_value DESC)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_customers_ltv_id "
        "ON customers_synced (lifetime_value DESC, customer_id)"
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with lakebase_sp() as conn:
            async with conn.cursor() as cur:
                for ddl in _INDEX_DDL:
                    await cur.execute(ddl)
            await conn.commit()
        log.info("startup: pagination indexes ensured")
    except Exception:
        log.warning("startup: could not ensure pagination indexes", exc_info=True)
    yield
    await close_pool()


app = FastAPI(title="Customer 360", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# OpenTelemetry request tracing. The `opentelemetry-instrument` command wrapper
# (app.yaml) already auto-instruments when deployed; instrumenting the app
# instance here means local `uvicorn` runs are traced too, and is a no-op if the
# wrapper already instrumented it. Guarded so a telemetry-less env still boots;
# `trace` stays None then, and the request-id span stamping below is skipped.
try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="assets/.*")
except Exception:
    trace = None
    log.warning("OpenTelemetry FastAPI instrumentation unavailable", exc_info=True)


@app.exception_handler(PermissionError)
async def permission_error_handler(_: Request, exc: PermissionError):
    # OBO header missing / consent not granted → 401, not a 500.
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    # Correlate the request id with the OTel trace so a log/trace lookup by
    # X-Request-Id resolves the whole React → FastAPI → Lakebase/SQL span tree.
    if trace is not None:
        trace.get_current_span().set_attribute("request.id", rid)
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    # Idempotent API GETs are privately cacheable so back/forward navigation is
    # free; must-revalidate keeps writes from being served stale. TanStack Query
    # staleTimes remain the primary client-side control (see lib/queries.ts).
    if (
        request.method == "GET"
        and request.url.path.startswith("/api/")
        and 200 <= response.status_code < 300
        and "cache-control" not in response.headers
    ):
        response.headers["Cache-Control"] = "private, max-age=30, must-revalidate"
    return response


app.include_router(customers.router)
app.include_router(dashboard.router)
app.include_router(genie.router)
app.include_router(jobs.router)

# Serve the built SPA. Hashed assets are served from /assets; every other
# non-API path falls back to index.html so client-side routes (e.g.
# /customers/{id}) resolve on deep-link and refresh, not just in-app nav.
if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    _INDEX = _STATIC_DIR / "index.html"

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_INDEX)
