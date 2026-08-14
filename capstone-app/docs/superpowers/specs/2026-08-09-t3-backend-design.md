# T3 (backend) — App APIs

## Scope

The **backend half** of T3: five FastAPI endpoints exercising the read/write
patterns the training covers. The React UI is a separate stacked PR
(`t3-frontend`) on top of this one. T3a (external M2M) is deferred until after
T8 — its done-checks need a deployed app URL + CAN_USE grant, untestable
locally.

Stacked: `t3-backend` → `t2-auth`.

## Decisions (from brainstorming)

- **Async DB layer.** T2 shipped a *sync* pool; T3 reworks `db.py` to
  `psycopg_pool.AsyncConnectionPool` so endpoints are `async def` and the
  detail page can fan out concurrently — matching the Optimizations guidance.
  The rework lands *here* (not amended into merged `t2-auth`); T2's live tests
  are updated to async in the same PR.
- **Offset pagination** with a `COUNT(*)` total → the required
  `{items, total, page, page_size}` shape directly. 10k rows sorts fast;
  supported by a composite index (below).
- **Index on the synced table.** `CREATE INDEX IF NOT EXISTS
  idx_customers_seg_ltv ON customers_synced (segment_id, lifetime_value DESC)`
  — **verified working** on a synced table (reads/indexes/DROP are the allowed
  operations; only data modification breaks sync). Created idempotently at
  app startup so a full re-sync can't leave it missing.
- **Metrics** uses the SQL warehouse via **OBO** (only OBO path in T3), built
  and live-test-gated like the others.

## Data paths (verified against the live workspace)

Lakebase `public` has: `customers_synced`, `transactions_synced`,
`products_synced` (read via SP) + `customer_notes_staging`,
`customer_segment_overrides_staging`, `customer_audit_log` (read/write via SP).
`customer_segments` and `support_tickets` are **warehouse-only** (not synced) —
which is *why* Metrics must take the warehouse path (it joins
transactions × products × support_tickets and resolves the segment name).

## Files

```
app/backend/
  main.py               # FastAPI app: lifespan, middleware, router mount, static, startup index
  db.py                 # async: AsyncConnectionPool + async lakebase_sp() + close_pool()
  deps.py               # FastAPI dependency providers (DI) — see below
  models.py             # SQLModel classes (schema + API shapes) + API-only models
  routers/__init__.py
  routers/customers.py  # the 5 endpoints
```

## Dependency injection (`deps.py`)

Follow FastAPI DI idiom: handlers declare what they need via `Depends()` and
never touch globals or parse the raw request themselves. Providers, each with
an `Annotated` type alias for terse signatures:

- `DbConn` — `async def get_db()` yields a pooled connection from
  `lakebase_sp()` (the pool's own context manager handles
  checkout/return). Handlers take `conn: DbConn`.
- `Obo` — `def get_obo_client(request) -> WorkspaceClient` wraps the current
  header-reading logic; the *only* place `Request` is touched. Handlers that
  hit the warehouse take `obo: Obo`.
- `Actor` — `def get_actor_email(request) -> str` for the audit trail.
  Write handlers take `actor: Actor`.
- `Settings` — `def get_settings_dep()` returns the cached settings, so config
  is injected rather than imported ad hoc.
- Query-param models (`CustomerFilters`, `PageParams`) are declared as
  dependency classes (`Depends()`), so pagination/filter parsing +
  validation (`page_size` cap → 422) is reused, not repeated per endpoint.

`sp_client()` stays a module singleton but is consumed *through* the `DbConn`
provider (and injected directly where a handler needs the SP client itself),
so tests can override any of these with `app.dependency_overrides`.

## Endpoints (`routers/customers.py`, prefix `/api`)

| Method + Path | Auth/path | Behaviour |
|---|---|---|
| `GET /customers` | Lakebase SP | Params via injected `CustomerFilters` (`segment`, `min_ltv`, `max_churn`) + `PageParams` (`page` ≥ 1; `page_size` default 25, `le=100` so > 100 → **422**). `COUNT(*)` + `SELECT … ORDER BY lifetime_value DESC OFFSET … LIMIT …`, all params bound. Returns `Page[CustomerSummary]`. |
| `GET /customers/{id}` | Lakebase SP | Profile from `customers_synced` (404 if absent) + last 20 from `transactions_synced` (`ORDER BY transaction_date DESC LIMIT 20`). One connection, two queries. Returns `CustomerDetail`. |
| `GET /customers/{id}/metrics` | **Warehouse + OBO** | Injects `obo: Obo` → `obo.statement_execution.execute_statement` against gold. Lifetime spend, top-5 categories, 30/90-day totals, open-ticket count, avg CSAT, segment name. Returns `CustomerMetrics`. |
| `POST /customers/{id}/notes` | Lakebase SP | **Single transaction**: INSERT into `customer_notes_staging` + INSERT into `customer_audit_log` (`action='add_note'`, `actor: Actor`, payload JSONB). Returns `NoteOut`. |
| `POST /customers/{id}/segment` | Lakebase SP | Single transaction: `INSERT … ON CONFLICT (customer_id) DO UPDATE SET …` into `customer_segment_overrides_staging` + audit row (`action='override_segment'`). Idempotent by the T1 unique constraint — re-submitting the same value updates in place, never a duplicate. |

## Models (`models.py`) — SQLModel

Use **SQLModel** (`sqlmodel` dep) so each class is *both* the Pydantic model
(API request/response shape, OpenAPI-documented) and the table definition
(single source of truth for schema). `table=True` classes for the persisted
tables: `CustomerSynced` (`customers_synced`), `TransactionSynced`
(`transactions_synced`), `CustomerNote` (`customer_notes_staging`),
`SegmentOverride` (`customer_segment_overrides_staging`), `AuditLog`
(`customer_audit_log`) — field names/types mirror the verified live columns,
`__tablename__` pinned to the real names.

**Queries still run through T2's async psycopg token pool** (see decision
below) — the ORM classes are *not* driving an SQLAlchemy engine. Handlers
receive a pooled connection via the injected `conn: DbConn` (the `get_db`
provider is the sole caller of `lakebase_sp()`), execute bound SQL with a
`dict_row` row factory, and validate the resulting dicts into the SQLModel
classes (`CustomerSynced.model_validate(row)`). This keeps the
OAuth-per-connection token minting from T2 untouched while giving us typed
models as the schema/response contract.

API-only (non-`table`) models: `Page[T]` (generic: `items`, `total`, `page`,
`page_size`), `NoteIn`, `SegmentOverrideIn`, `CustomerMetrics`,
`CustomerDetail` (a `CustomerSynced` + `list[TransactionSynced]` composite).
All handlers set `response_model=` so shapes are enforced.

**Why not a full SQLAlchemy ORM engine:** the async ORM needs its own engine,
which would displace T2's `AsyncConnectionPool` and move token minting into a
`do_connect` hook. Since synced tables are read-only and writes are two-table
transactions we already express cleanly in SQL, the pool + SQLModel-as-schema
split is the lower-risk fit. Documented as a deliberate choice.

## `main.py` hygiene (Optimizations applied now)

- `GZipMiddleware(minimum_size=1000)`.
- `X-Request-Id` middleware: generate if missing, echo back.
- Structured logger (`logging.getLogger`); log Lakebase/warehouse queries over
  ~500ms at WARNING.
- Lifespan: create the index at startup, close the pool on shutdown.
- Mount the `/api` router; serve `backend/static` (SPA) for everything else.
- `Cache-Control: private, max-age=…` on idempotent GETs.

## Verification (Done-when → tests)

Live pytest via FastAPI `TestClient`. Auth deps (`Obo`, `Actor`) are supplied
via `app.dependency_overrides` where a test needs a specific identity; the
real header-reading path is covered by injecting a request with
`X-Forwarded-*` set. Skip without Databricks auth, per the existing `live`
marker:

- List returns the page shape; `page_size=101` → **422**; filters narrow results.
- Detail: known id → profile + ≤ 20 transactions; unknown id → **404**.
- Note write → response ok **and** a matching `customer_audit_log` row exists.
- Segment override submitted **twice** with the same value → exactly one row in
  `customer_segment_overrides_staging` (idempotency).
- Metrics: known id → non-null aggregates (live warehouse assertion).

Async tests use `pytest-asyncio` (new dev-dep); T2's two live DB tests are
migrated to async against the reworked pool.

## Out of scope

- React UI → `t3-frontend`.
- External M2M endpoint + `examples/` → T3a (post-T8).
- `app.yaml` env/scope wiring → T6.
