# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React 18 + Vite + TypeScript + TanStack Query (React Router 6), with
**shadcn/ui** for components (user-directed). Frontend lives in `app/frontend/`,
builds to `app/backend/static/`, and talks to a FastAPI backend under `/api`
(dev server proxies `/api` → uvicorn:8000). Backend endpoints are already built
(T3 backend PR).

## Users

**Customer-success reps at Acme Retail** (a synthetic 10k-customer retail
dataset). They work inside the app to understand and act on customer insights
without leaving the tool: browse accounts, open a 360° view, leave notes,
override segments, ask ad-hoc questions, and run data jobs. Signed in
automatically via the Databricks Apps OBO proxy — no login screen.

## Product Purpose

A "Customer 360" operational console. Reps filter and browse the customer base,
drill into a per-customer view (profile, computed metrics, recent activity,
notes, segment overrides), consult an embedded analytics dashboard, ask Genie
natural-language questions, and trigger a forward-ETL job that promotes their
staged writes into gold. Success = a rep can find a customer, understand their
state, and act (note/override) in seconds, with every write audited.

## Positioning

Built directly on Databricks Apps + Lakebase: sub-10ms reads from Lakebase
synced tables, write-back to Lakebase staging with transactional audit, live
cross-table metrics via the SQL warehouse under the calling user's identity
(OBO), plus in-app Genie and an embedded AI/BI dashboard — one operational
surface over the lakehouse, not a separate BI export.

## Operating Context

Six surfaces (routes), left-sidebar navigation, top app bar showing the
signed-in user's email + a workspace badge, and a floating "Ask Genie" button
bottom-right on every page:

1. **Customers** (`/`, landing) — filterable, server-paginated list; row →
   detail.
2. **Customer detail** (`/customers/:id`) — tabs: Profile · Metrics · Activity
   · Notes · Segment override.
3. **Dashboard** (`/dashboard`) — embedded AI/BI dashboard (T4).
4. **Reports** (`/reports`) — "Run forward-ETL" + run status + recent runs (T7).
5. **Genie** — floating overlay chat, not a route (T5).

This frontend PR (`t3-frontend`) delivers the **Customers list + Customer
detail** pages against the live T3 backend; Dashboard, Reports, and Genie land
in their own later PRs but the app shell must leave room for them.

## Capabilities and Constraints

- **Backend endpoints (live):** `GET /api/customers` (paginated
  `{items,total,page,page_size}`, filters `segment`/`min_ltv`/`max_churn`,
  `page_size` cap 100 → 422); `GET /api/customers/{id}` (profile + last 20
  transactions); `GET /api/customers/{id}/metrics` (warehouse-computed:
  lifetime spend, top-5 categories, 30/90-day spend, open tickets, avg CSAT,
  segment name); `POST /api/customers/{id}/notes`; `POST
  /api/customers/{id}/segment` (idempotent upsert).
- **Data shapes:** customers have id (e.g. `C0003600`), name, email, phone,
  country/city, age, gender, signup/last-purchase dates, `segment_id` (S1–S7),
  `lifetime_value`, `churn_score` (0–1). Segments: Champions, Loyal, At Risk,
  Potential Loyalists, Hibernating, … Transactions: date, channel
  (web/mobile/store), status (completed/pending/cancelled), amount.
- **Engineering bar (reviewers grade on it):** server-side pagination (never
  ship 10k rows), TanStack Query caching with per-key `staleTime`, parallel
  fan-out of detail-tab fetches, debounced filter inputs, route code-splitting,
  optimistic invalidation after writes, real loading/error/empty states.
- Metrics is the slow path (~seconds, warehouse); list/detail are fast
  (Lakebase).

## Brand Commitments

"Acme Retail" is a synthetic demo tenant — not a real brand, no real logo or
identity to honor. The app is an internal tool built for a Databricks
certification review, judged on polish and production-grade craft. No binding
external brand constraints; visual world is open (decided in new-work).

## Evidence on Hand

- Authoritative spec: `capstone-app/CAPSTONE_TASKS.md` (tasks, data schemas,
  done-criteria, optimization bar).
- Live backend on the `fevm-test-jg` workspace with real synthetic data (10k
  customers, ~100k transactions, 200 products, 7 segments, support tickets).
- No real customer data, testimonials, or external brand assets — do not
  fabricate any.

## Product Principles

1. **Operate, don't decorate** — this is a rep's working console; scanability,
   speed, and correct states beat expression. Brand lives in precise detail.
2. **Every write is audited and safe** — notes/overrides are transactional;
   the UI should make the audit trail and idempotency legible, never surprising.
3. **Identity is the user's** — reads/writes attribute to the signed-in rep
   (shown in the app bar); the app never pretends to be someone else.
4. **Fast where it can be, honest where it can't** — Lakebase reads feel
   instant; the warehouse metrics path shows its own loading state rather than
   blocking the page.
5. **Leave room for the whole journey** — the shell must accommodate Dashboard,
   Reports, and the Genie overlay even though this PR ships only Customers +
   Detail.

## Accessibility & Inclusion

Standard operational-tool expectations: keyboard-navigable table and forms,
visible focus, adequate contrast in both light and dark, and semantic status
color (churn risk, ticket state) that never relies on hue alone.
