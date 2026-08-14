# Optimizations & engineering-hygiene writeup

How the production-grade patterns from the *Optimizations & engineering
hygiene* section are implemented. File references are to `app/`.

## Pagination

- **Envelope:** list endpoints return `{ items, total, page, page_size,
  next_cursor }` (`backend/models.py` `Page[T]`). `page_size` defaults to 25,
  is hard-capped at 100 by `Query(25, ge=1, le=100)`, and >100 is rejected
  with 422 (`backend/deps.py` `PageParams`).
- **Keyset pagination** (`backend/routers/customers.py` `list_customers`):
  the default sort is `lifetime_value DESC, customer_id`. When a client passes
  `?after=<cursor>`, the endpoint seeks by keyset
  (`lifetime_value < :cx OR (lifetime_value = :cx AND customer_id > :cid)`)
  instead of `OFFSET`, so deep pages don't scan-and-discard. The cursor is an
  opaque base64 of the last row's sort key. We over-fetch one row to decide
  whether to emit `next_cursor` (null on the last page) without a second query.
  OFFSET remains available for direct page jumps.
- **Frontend** (`frontend/src/pages/Customers.tsx`): a cursor stack drives
  Prev/Next — Next pushes `next_cursor`, Prev pops (replaying a cached page),
  so back-navigation never re-scans.
- **Indexes** (`backend/main.py` startup DDL): `idx_customers_ltv_id`
  `(lifetime_value DESC, customer_id)` backs the unfiltered keyset seek;
  `idx_customers_seg_ltv` `(segment_id, lifetime_value DESC)` backs the
  segment-filtered sort.

## Caching

- **Server-side:** `/api/config` and `/api/dashboard/analytics` are cached with
  `cachetools.TTLCache` (5 min), keyed once — no per-customer server cache
  (`backend/routers/dashboard.py`). The analytics payload is only cached when
  non-empty so a warehouse timeout retries live.
- **Client-side:** every GET is a TanStack Query with tiered `staleTime`
  (`frontend/src/lib/queries.ts`): list 10s, detail 30s, metrics 60s,
  config 5 min. Mutations `invalidateQueries` the affected keys.
- **Browser:** idempotent `/api/**` GETs get
  `Cache-Control: private, max-age=30, must-revalidate`
  (`backend/main.py` middleware) so back/forward navigation is free.

## Connection pooling (Lakebase)

`backend/db.py` uses `psycopg_pool.AsyncConnectionPool` (min 1 / max 5) with a
pre-ping check. Rather than a background refresh thread, we **mint a fresh
OAuth token on every physical connect** and cap `max_lifetime` at 45 min
(below the ~1 h token TTL), so every pooled connection is always backed by a
valid token.

## React performance

- Routes are code-split with `React.lazy` + `<Suspense>` (`frontend/src/main.tsx`)
  — the build emits separate `Customers` / `CustomerDetail` / `Dashboard` /
  `Reports` chunks.
- The list grid row is `React.memo`'d with a stable `customer_id` key and a
  `useCallback` row handler, so paging only re-renders changed rows.
- Filter inputs are debounced 250 ms (`frontend/src/lib/useDebounced.ts`).
- The detail page fans out the profile and (expensive) metrics queries from
  first render (`CustomerDetail.tsx`), and metrics runs its four warehouse
  aggregates in parallel via `asyncio.gather`.

## API hygiene

- `GZipMiddleware(minimum_size=1000)` (`backend/main.py`).
- No `SELECT *`: the list ships a slim `CustomerSummary` projection; detail /
  activity ship explicit column lists (`backend/routers/customers.py`).
- Pydantic/SQLModel response models on every endpoint (documented in OpenAPI).
- Outbound timeouts: warehouse calls use `wait_timeout="30s"`; Genie and Jobs
  SDK calls are bounded by `asyncio.wait_for(..., 30s)` → 504 on timeout
  (`backend/routers/genie.py`, `jobs.py`).

## Observability

OpenTelemetry auto-instrumentation per the
[Databricks Apps observability guide](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/observability?language=FastAPI):
`app.yaml` wraps uvicorn with `opentelemetry-instrument` and sets
`OTEL_TRACES_SAMPLER=always_on`; the Apps runtime injects the OTLP endpoint and
exports traces/metrics/logs to the workspace `otel_spans` / `otel_metrics` /
`otel_logs` tables. `FastAPIInstrumentor.instrument_app(app)` also traces local
runs. Each request's `X-Request-Id` is echoed back and stamped onto the active
span (`request.id`), so a lookup by request id resolves the whole
React → FastAPI → Lakebase/SQL trace; per-request span durations make slow
requests (and the queries inside them) queryable in `otel_spans`.
