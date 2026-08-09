# T4 — Analytics dashboard (native rebuild) — design

**Date:** 2026-08-09
**Task:** CAPSTONE_TASKS.md T4 ("Embed the AI/BI dashboard")
**Stacked on:** t3-frontend → t3-backend → …

## Decision & deviation from the task text

The task literally asks to **iframe-embed** the provisioned AI/BI dashboard
(`/embed/dashboardsv3/${dashboard_id}`). We are instead **rebuilding the five
dashboard charts natively** with shadcn/ui charts, themed to the night-flight
cockpit, because the raw embed clashes hard with the app's visual world (light
Databricks chrome dropped into a dark instrument panel — the user rejected it).

**Skill-coverage preservation.** T4 certifies the "Lakeview dashboard embed"
skill. To keep that skill visible on the submission despite the native rebuild,
we retain `GET /api/config` and surface an **"↳ Open in AI/BI workspace"**
deep-link on the dashboard header (`${host}/dashboardsv3/${dashboard_id}`). The
writeup will call out this deviation explicitly. If reviewers require the actual
iframe, it can be reinstated on a secondary tab cheaply — `/api/config` already
carries everything it needs.

## Source of truth — the real dashboard SQL

Pulled live from the provisioned dashboard
(`01f19331dc2e190cbba8dc3f1cbe1c26`, catalog `test_jg_catalog.gold`). Four
datasets back the five charts:

1. **Customers by Segment** (backs *Avg LTV by Segment* AND *Avg Churn by Segment*):
   ```sql
   SELECT s.segment_name, COUNT(*) AS customers,
          ROUND(AVG(c.lifetime_value), 2) AS avg_ltv,
          ROUND(AVG(c.churn_score), 3) AS avg_churn
   FROM gold.customers c
   JOIN gold.customer_segments s ON c.segment_id = s.segment_id
   GROUP BY s.segment_name ORDER BY avg_ltv DESC
   ```
2. **Top products by revenue** (LIMIT 15, completed txns only):
   ```sql
   SELECT p.name AS product_name, p.category,
          ROUND(SUM(t.amount), 2) AS revenue, COUNT(*) AS units
   FROM gold.transactions t JOIN gold.products p ON t.product_id = p.product_id
   WHERE t.status = 'completed'
   GROUP BY p.name, p.category ORDER BY revenue DESC LIMIT 15
   ```
3. **Support tickets by week** (multi-line by category):
   ```sql
   SELECT DATE_TRUNC('week', opened_at) AS week, category, COUNT(*) AS tickets
   FROM gold.support_tickets
   GROUP BY DATE_TRUNC('week', opened_at), category ORDER BY week
   ```
4. **Churn-risk distribution** (0.1-width buckets):
   ```sql
   SELECT ROUND(FLOOR(churn_score * 10) / 10, 1) AS bucket, COUNT(*) AS customers
   FROM gold.customers
   GROUP BY ROUND(FLOOR(churn_score * 10) / 10, 1) ORDER BY bucket
   ```

## Backend

New router `app/backend/routers/dashboard.py`:

- **`GET /api/dashboard/analytics`** — runs the four aggregates on the SQL
  warehouse via **OBO** (calling user's `X-Forwarded-Access-Token`), consistent
  with the existing metrics endpoint. Fan out with `asyncio.gather` +
  `asyncio.to_thread`. Returns one typed payload:
  `{ segments: [...], products: [...], tickets: [...], churn_buckets: [...] }`.
  - Add a param-less `_run_sql(w, sql)` sibling to the metrics
    `_run_stmt(w, sql, customer_id)` (these queries bind no parameters). Reuses
    the same `warehouse_id` / catalog / schema from `Settings`.
  - Pydantic response models (`SegmentAgg`, `ProductRevenue`, `TicketWeek`,
    `ChurnBucket`, `DashboardAnalytics`) → enforced + OpenAPI-documented.
- **`GET /api/config`** — returns `{ databricks_host, dashboard_id,
  genie_space_id }` from `Settings`. Full config now (T5 reuses it untouched).
  No auth, no DB.
  - Add `dashboard_id` + `genie_space_id` fields to `config.py` (host already
    present). Values live in `app/.env`.
- **Caching:** the analytics payload is slow-changing org-wide analytics →
  `cachetools.TTLCache(maxsize=1, ttl=300)` (rubric-endorsed target). `/api/config`
  is static → same 5-min TTL cache (or plain module constant; TTLCache chosen
  because the rubric names it).
- Register both routes in `main.py`.

## Frontend

`Dashboard.tsx` replaces the `/dashboard` `ComingSoon` route:

- Header placard + **"↳ Open in AI/BI workspace"** deep-link (from `/api/config`).
- **Five cockpit-bezel instrument cards** on the panel grid, charts via
  **shadcn/ui charts (Recharts)** themed to the night-flight palette:
  - Avg LTV by Segment — bar (radio-green)
  - Avg Churn by Segment — bar (amber→alert as score rises)
  - Top 15 Products by Revenue — bar
  - Weekly Support Tickets — multi-line (billing / returns / shipping)
  - Churn-Risk Distribution — histogram (alert tint on the 0.8+ spike)
- Add deps: `recharts` + shadcn `chart` primitive. JetBrains Mono axis
  readouts, bezel frames, grain overlay — reuse existing tokens/components.
- Data: `api.getDashboardAnalytics()` + `api.getConfig()` in `lib/api.ts`;
  `useDashboardAnalytics()` (`staleTime: 60s`) + `useConfig()` (`staleTime: 5m`)
  in `queries.ts`; `AppConfig` + analytics types in `types.ts`.
- **States:** loading skeletons; **amber caution card** (not the red "Signal
  lost") when analytics is absent — locally there's no OBO token so the page
  shows this, identical to the Metrics-tab caveat. Deep-link is the escape hatch.
- Wire lazy route in `main.tsx`.

## Explicitly NOT doing

- No iframe embed in the primary view (deep-link preserves the skill on record).
- No dark-theming of any embedded Databricks surface.
- No new Genie work — only `genie_space_id` added to config (that's T5).

## Verify

- `GET /api/config` returns the 3 fields (curl).
- `GET /api/dashboard/analytics` returns the 4 arrays with an OBO token
  (curl with injected `X-Forwarded-Access-Token`); 401 without (PermissionError
  handler).
- Dashboard route renders 5 themed charts with live data (deployed / token
  injected); amber caution card locally.
- ruff format + check clean; `tsc --noEmit` clean.
