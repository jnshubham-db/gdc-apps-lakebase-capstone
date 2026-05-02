# Capstone — Customer 360 on Databricks Apps + Lakebase

## What you're building

A "customer success" web app for **Acme Retail** (a synthetic 10k-customer
retail dataset, already provisioned in your workspace by the installer).
Reps use the app to:

- Browse customer accounts (list with filters: segment, LTV, churn risk)
- Open a 360° view (profile + last 20 transactions + computed metrics)
- Leave **notes** and override **segments** (writes go to Lakebase staging)
- Ask **Genie** ad-hoc questions
- View an embedded **AI/BI dashboard**
- Trigger a **forward-ETL** job that promotes staging rows into gold

A separate `/api/external/*` surface exposes the same data to partner
systems via two auth flows: **M2M** (service-principal client_credentials
→ OAuth access token) and **U2M** (user PAT). In both cases the client
uses the Databricks SDK to obtain a Bearer token and calls the endpoint
with `Authorization: Bearer <token>` — the Databricks Apps proxy
validates the token and forwards the caller's identity to your handler
via `X-Forwarded-Access-Token` (same mechanism as in-app OBO), so the
handler is the same code as the Detail endpoint.

---

## User journey

The app is for **customer success reps** who want to understand and act on
customer insights without leaving the tool. A typical session:

1. **Sign in** — automatic via OBO (the Databricks Apps proxy injects
   the user's identity); no login screen of your own.
2. **Customer list** (`/customers`) — the default landing page. Rep
   filters by segment, minimum LTV, maximum churn risk; clicks a row to
   drill in.
3. **Customer detail** (`/customers/:id`) — tabbed view:
   - **Profile** — name, contact, segment, signup date, churn score
   - **Metrics** — lifetime spend, top-5 categories, last-30 / 90-day
     totals, open ticket count, avg CSAT (computed live via SQL warehouse
     aggregation across multiple gold tables)
   - **Activity** — last 20 transactions
   - **Notes** — list existing notes + form to add a new one
   - **Segment override** — current segment + form to override
4. **Genie** (`/genie`) — chat box that answers ad-hoc questions
   ("Top 5 segments by LTV last quarter", "Which customers in EU have
   churn > 0.7?"). Also show a hover chat icon on the bottom right of the page.
5. **Dashboard** (`/dashboard`) — embedded AI/BI dashboard for broader
   analytics (segment LTV, top products, ticket trends, churn histogram).
6. **Reports** (`/reports`) — "Run forward-ETL" button + run-status
   indicator + history of recent runs.

---

## App design & UI requirements

Reviewers will judge the app on polish, update the below UI elements as per your design sense.
- FastAPI for backend and React for frontend. Use uv for project management. Create venv for local development.
- **Stack:** React 18 + Vite + TypeScript + MUI v6 (already pinned in
  `app/package.json`). Use [TanStack Query](https://tanstack.com/query)
  (React Query) for data fetching — it gives you caching, retries, and
  optimistic updates for free.
- **Theme:** modern, **teal-based** primary color (e.g. `#0D9488` —
  Tailwind teal-600 — or the MUI `teal[600]` swatch). Define this in
  `app/frontend/src/theme.ts` and wrap the app in MUI's `<ThemeProvider>`.
  Use a light surface palette with subtle shadows; avoid garish accent
  colors. The app should feel like a polished SaaS product, not a demo.
- **Layout:** persistent left sidebar nav (Customers, Genie, Dashboard,
  Reports), top app bar with the signed-in user's email and a workspace
  badge, content area in the middle.
- **Loading states:** skeleton placeholders (MUI `Skeleton`) while data
  is fetching — never a blank screen.
- **Empty / error states:** every list and form must handle the empty
  case ("No customers match the filter") and the error case (toast +
  retry button).
- **Responsive:** sidebar collapses to a hamburger below the `md`
  breakpoint; data grid adapts column visibility on narrow screens.

---

## What this capstone tests

Every skill from the Apps + Lakebase training:

- OBO + service-principal authentication
- Lakebase reverse ETL (synced tables) and writable staging tables
- Lakebase CRUD with audit, transactional safety
- SQL warehouse query from an App
- Genie Conversation API
- Lakeview dashboard embed
- `app.yaml` env + secrets binding + OBO scopes
- M2M + U2M authentication for external API surfaces
- Forward ETL (staging → gold)
- DABs + **git-source** app deployment with GitHub Actions
- Lakebase ops: branching, PITR, query insights

The repo-root **`README.md`** documents the `curl … | bash` installer
that has already provisioned: gold tables, Lakebase instance, AI/BI
dashboard, Genie space, and your `app/.env`. From here on out you write
the app.

## Prerequisites

- Databricks workspace access (UC enabled; can create Lakebase + apps).
- A Serverless SQL warehouse you can use (the installer let you pick one).
- `databricks` CLI ≥ 0.299, `uv`, `node` ≥ 20.
- Forked this scaffold into your own repo (private is fine) — required
  for **T8** (git-source app deployment).

---

## T1 — Reverse ETL: synced + staging tables

**Why this is needed:** Your app needs sub-10ms customer reads (Lakebase
*synced* tables, kept fresh from gold) AND a place to write notes /
segment overrides without touching gold (Lakebase *staging* tables).
This task wires both.

**Do this:**

- Create 3 Lakebase synced tables in **CONTINUOUS** mode (so writes to
  gold appear in Lakebase within seconds — required for the app to
  reflect upstream changes live):
  - `customers_synced` ← `<catalog>.gold.customers` (CONTINUOUS)
  - `transactions_synced` ← `<catalog>.gold.transactions` (CONTINUOUS)
  - `products_synced` ← `<catalog>.gold.products` (TRIGGERED hourly,
    because the catalog is slow-changing — justify this choice in your
    submission reflection)
- Create 3 writable staging tables in Lakebase via psycopg DDL:
  - `customer_notes_staging` (with `processed BOOLEAN DEFAULT false`)
  - `customer_segment_overrides_staging` (same)
  - `customer_audit_log` (append-only)


**Docs:**
- Synced tables: https://docs.databricks.com/aws/en/oltp/projects/sync-tables
- Lakebase Postgres connection: https://docs.databricks.com/aws/en/oltp/projects/external-apps-connect

**Done when:**
- [ ] All 3 synced tables show **CONTINUOUS** state in the Lakebase UI
- [ ] All 3 staging tables exist (`\dt` via psycopg) with the right columns

---

## T2 — Auth: OBO and service-principal clients

**Why:** Every Lakebase / SQL / Genie call needs an identity. **OBO**
carries the calling user's identity through the app to data services
(so workspace-level RLS and audit work). **SP** is for app-level work
that isn't tied to a user (background jobs, cron).

**Do this:** in `app/backend/auth.py`, implement:

- `obo_client(request) -> WorkspaceClient` — read
  `X-Forwarded-Access-Token` from the request and build a
  `WorkspaceClient(token=...)`
- `sp_client() -> WorkspaceClient` — module-level client using the
  app's service-principal credentials (provided by the runtime)

In `app/backend/db.py`, also implement two psycopg connection helpers
(`lakebase_obo(request)` and `lakebase_sp()`) that mint a fresh OAuth
token for Lakebase auth — Lakebase Postgres tokens are short-lived
(~1h), so re-mint on every checkout (or wrap in a pool with token
rotation; see the **Optimizations** section).

**Docs:**
- OBO + scopes: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth
- HTTP headers passed to apps: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/http-headers

**Cookbook:** https://apps-cookbook.dev/docs/streamlit/authentication/users_get_current

**Done when:**
- [ ] A test endpoint that calls `obo_client(request).current_user.me()` returns the *calling user* (not the SP)
- [ ] An endpoint using `sp_client()` runs as the service principal in audit logs
- [ ] `SELECT 1` against Lakebase via `lakebase_obo()` works

---

## T3 — App APIs + React UI

**Why:** These endpoints exercise every read/write pattern the training
covers — Lakebase synced reads, SQL warehouse for cross-table aggregates,
Lakebase staging writes with audit, and dual-auth external access.

### Backend endpoints

| Group | Method + Path | What it does | Skill |
|---|---|---|---|
| **Reads** | `GET /api/customers?segment=&min_ltv=&max_churn=&page=&page_size=` | Paginated list from `customers_synced` (Lakebase via OBO). Server-side pagination + filtering. | Lakebase synced reads |
| | `GET /api/customers/{id}` | Profile from `customers_synced` + last 20 from `transactions_synced` (Lakebase via OBO). | Lakebase synced reads |
| **Writes** (transactional + audited) | `POST /api/customers/{id}/notes` | INSERT into `customer_notes_staging` AND append a row to `customer_audit_log` in the **same transaction**. | Lakebase CRUD + audit |
| | `POST /api/customers/{id}/segment` | UPSERT into `customer_segment_overrides_staging` AND append to `customer_audit_log` in the same transaction. | Lakebase CRUD + audit |
| **External** | `GET /api/external/customers/{id}` | Same payload as Detail, exposed for partner systems. Handler is **the same code as Detail** — reads `X-Forwarded-Access-Token` (the Apps proxy validates the Bearer for you). Test from outside the app with two Python scripts: one minting an M2M Bearer (SP client-credentials), one minting a U2M Bearer (user PAT). | M2M + U2M |

### How the External endpoint authenticates

The `/api/external/customers/{id}` handler is **identical in code** to
your OBO Detail handler — both read `X-Forwarded-Access-Token` from the
incoming request to obtain the caller's identity and act on their behalf
against Lakebase. **What changes is who's calling and how they obtain a
Bearer token**, not how the handler authenticates.

**The Databricks Apps proxy is the auth boundary.** When any client
sends `Authorization: Bearer <token>` to your app's URL, the Apps proxy
validates the token and forwards the request to your FastAPI handler
with the caller's identity in `X-Forwarded-Access-Token` (alongside
`X-Forwarded-User`, `X-Forwarded-Email`). Your handler doesn't do its
own bearer parsing or token introspection — it just trusts the
forwarded headers, exactly like in-browser OBO requests.

**Use the Databricks SDK to get a Bearer.** Whether the auth is PAT
(U2M) or client_credentials (M2M), the SDK gives you back the same
shape — a Bearer token via `WorkspaceClient.config.authenticate()`:

```python
# examples/_token.py — shared helper
from databricks.sdk import WorkspaceClient

def get_bearer(**kwargs) -> str:
    """Mint a Bearer token via the Databricks SDK.

    M2M: get_bearer(host=H, client_id=CID, client_secret=SEC)
         (SDK runs the client_credentials OAuth grant and returns the
         access_token; you NEVER pass the client_secret as the bearer)

    U2M: get_bearer(host=H, token=PAT, auth_type='pat')
         (SDK wraps the PAT in the Authorization header as-is)
    """
    w = WorkspaceClient(**kwargs)
    headers = w.config.authenticate()
    return headers["Authorization"].replace("Bearer ", "")
```

Provide two Python test scripts in `examples/` that use this helper to
mint the right token and call `/api/external/customers/{id}`:

- **`examples/m2m_test.py` (M2M — service principal):**
  ```python
  import os, requests
  from _token import get_bearer

  HOST = os.environ["DATABRICKS_HOST"].rstrip("/")     # https://<workspace>.cloud.databricks.com
  APP  = os.environ["APP_URL"].rstrip("/")             # https://<app>.databricksapps.com

  token = get_bearer(
      host=HOST,
      client_id=os.environ["DATABRICKS_CLIENT_ID"],
      client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
  )
  r = requests.get(
      f"{APP}/api/external/customers/C0000001",
      headers={"Authorization": f"Bearer {token}"},
  )
  print(r.status_code, r.json())
  ```

- **`examples/u2m_test.py` (U2M — end user PAT):**
  ```python
  import os, requests
  from _token import get_bearer

  token = get_bearer(
      host=os.environ["DATABRICKS_HOST"].rstrip("/"),
      token=os.environ["DATABRICKS_PAT"],
      auth_type="pat",
  )
  r = requests.get(
      f"{os.environ['APP_URL'].rstrip('/')}/api/external/customers/C0000001",
      headers={"Authorization": f"Bearer {token}"},
  )
  print(r.status_code, r.json())
  ```

**Hints / gotchas:**

- **You cannot pass the SP's `client_secret` directly as the Bearer.**
  The proxy will reject it. The SDK does the `client_credentials` OAuth
  grant under the hood and gives you back the resulting OAuth
  `access_token` — that's what goes in the `Authorization: Bearer …`
  header.
- **For U2M you can pass the PAT directly** (the SDK with
  `auth_type="pat"` just wraps it as the Bearer). The user creates the
  PAT once in their workspace user settings; treat it like a password.
- **Both identities need app access.** In the workspace UI, open your
  app → **Permissions** → add the SP (for M2M) and the user (for U2M)
  with **CAN_USE**. Without this the proxy returns **403** even with a
  valid token.
- **Tokens are short-lived** (M2M OAuth ~1h; PATs longer but rotatable).
  Re-mint per script run; don't cache forever.
- **Never commit secrets.** Scripts read `DATABRICKS_HOST`, `APP_URL`,
  `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` (M2M), and
  `DATABRICKS_PAT` (U2M) from env vars.
- **Capture the JSON response** from each script run for your
  submission writeup — reviewers want to see both flows actually
  worked end-to-end.

### React UI

| Page | Endpoints used | Notes |
|---|---|---|
| `Customers.tsx` | List | MUI DataGrid + filter form; clicking a row navigates to detail. Server-side pagination (don't ship 10k rows). |
| `CustomerDetail.tsx` | Detail, Add note, Override segment | Tabs: Profile · Activity · Notes · Segment. Fan out the per-tab fetches in parallel with `Promise.all` / `useQueries`. |
| (External endpoint) | — | No UI; exercised from `examples/m2m_test.py` and `examples/u2m_test.py` (outputs saved into the writeup) |

**Files:**
- Backend: `app/backend/main.py`, `app/backend/db.py`, `app/backend/routers/customers.py`, `app/backend/routers/external.py`
- Frontend: `app/frontend/src/pages/Customers.tsx`, `app/frontend/src/pages/CustomerDetail.tsx`, `app/frontend/src/api/client.ts`
- External test scripts: `examples/_token.py`, `examples/m2m_test.py`, `examples/u2m_test.py`

**Docs:**
- SQL Statement Execution: https://docs.databricks.com/aws/en/dev-tools/sql-execution-tutorial
- Lakebase from Apps: https://docs.databricks.com/aws/en/oltp/projects/databricks-apps
- Apps HTTP headers (`X-Forwarded-Access-Token`): https://docs.databricks.com/aws/en/dev-tools/databricks-apps/http-headers
- M2M (SP OAuth client-credentials): https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m
- PAT (used as the U2M Bearer): https://docs.databricks.com/aws/en/dev-tools/auth/pat
- Databricks SDK auth (`WorkspaceClient` + `auth_type`): https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html

**Cookbook:**
- SQL warehouse + tables: https://apps-cookbook.dev/docs/streamlit/tables/tables_edit
- Auth recipes: https://apps-cookbook.dev/docs/streamlit/authentication/users_get_current

**Done when:**
- [ ] All 5 endpoints return the correct shape; in-app endpoints tested via the React UI, External tested via the two Python scripts
- [ ] Customer list paginates server-side (page-size cap enforced; never returns all 10k rows in one response)
- [ ] Adding a note appears in the list immediately AND a row exists in `customer_audit_log` for every write
- [ ] Overriding a segment is idempotent (re-submitting the same value is a no-op, not a duplicate row)
- [ ] `examples/m2m_test.py` and `examples/u2m_test.py` both return `200` + the customer JSON; stdout captured for the writeup
- [ ] Sanity check: passing the SP's `client_secret` directly as the Bearer (no SDK / no OAuth dance) returns `401` from the proxy — proves the OAuth flow is what actually authenticates M2M

---

## T4 — Embed the AI/BI dashboard

**Why:** Reps want broader analytics in-app without leaving for the
workspace UI. iframe embed is the supported integration pattern.

**Do this:**

- Add `GET /api/config` returning `{databricks_host, dashboard_id}`
- In `Dashboard.tsx`, fetch `/api/config` and render an `<iframe>`
  pointing at `${host}/embed/dashboardsv3/${dashboard_id}`

**Files:** `app/backend/main.py`, `app/frontend/src/pages/Dashboard.tsx`

**Docs:** https://www.databricks.com/blog/how-embed-aibi-dashboards-your-websites-and-applications

**Done when:**
- [ ] Dashboard renders inside the app and displays data (no "blocked by
      X-Frame-Options" or auth errors in the browser console)

---

## T5 — Integrate Genie chat

**Why:** Reps want to ask ad-hoc questions ("which segments saw
declining LTV in Q3?") in plain English. Genie's conversation API drives
the chat UX.

**Do this:** in `app/backend/routers/genie.py`, build three OBO endpoints:

- `POST /api/genie/conversations` → `genie.start_conversation`
- `POST /api/genie/conversations/{id}/messages` → `genie.create_message`
- `GET /api/genie/conversations/{id}/messages/{msg_id}` → `genie.get_message`
  (poll until status terminal; if it has an attachment, fetch the
  attachment query result)

Wire `Genie.tsx` to call these in a loop and stream the answer + tabular
preview into the chat. Show a typing indicator while polling; cap polls
at ~30s and surface a friendly error if the message never reaches a
terminal state.

**Files:** `app/backend/routers/genie.py`, `app/frontend/src/pages/Genie.tsx`

**Docs:** https://docs.databricks.com/aws/en/genie/conversation-api

**Cookbook:** https://apps-cookbook.dev/docs/streamlit/bi/genie_api

**Done when:**
- [ ] "Top segment by LTV" returns an answer + a result preview
- [ ] Follow-up questions in the same conversation maintain context

---

## T6 — App configuration: `app.yaml`

**Why:** `app.yaml` is the single config that ties the deployed app to
the resources you provisioned. Without it: missing secrets at runtime,
OBO scope mismatches, and Lakebase auth failure. Three blocks need to
be right:

- `env` — wire static + dynamic env vars: `PGHOST`, `PGDATABASE`,
  `WAREHOUSE_ID`, `DASHBOARD_ID`, `GENIE_SPACE_ID`, `PARENT_PATH`,
  `PG_UC_CATALOG`, etc. (read these from your `app/.env`)
- `secrets` — bind `pg_user`, `pg_password` from the secret scope
  the installer created (`SECRET_SCOPE` in your `.env`) into env vars
- `user_authorization` (OBO scopes) — list the OAuth scopes your app
  must request from the calling user. At minimum:
  `sql`, `dashboards.genie`, `dashboards`, `iam.access-control:read`.
  **OBO will silently fail** for any service whose scope isn't listed.

**Files:** `app/app.yaml`

**Docs:**
- App runtime config: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime
- Env vars + secrets binding: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables
- Resources binding: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources
- OBO scopes: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth

**Done when:**
- [ ] App starts with no missing-secret errors
- [ ] `obo_client()` can call SQL warehouse, Lakebase, and Genie without 401s

---

## T7 — Forward ETL: staging → gold

**Why:** Notes and overrides the app writes go into Lakebase staging.
To materialise them into Delta gold (for analytics, ML, audit) you need
a forward-ETL flow that propagates staging rows into gold. Two
architectures are accepted — pull-based and batched (Pattern A) or
push-based and CDC-streamed (Pattern B) — and the "Run forward-ETL"
button on your Reports page triggers the relevant compute in each.

**Do this — pick ONE pattern:**

- **Pattern A — psycopg + MERGE INTO Delta (pull, on-demand):**
  Notebook job in `lakebase/forward_etl/pattern_a_psycopg2/`. Connect
  to Lakebase via psycopg as the SP, read `*_staging WHERE processed=false`,
  build a Spark DataFrame, `MERGE INTO gold.customer_notes ON ...`, then
  `UPDATE *_staging SET processed=true WHERE id IN (...)` in the same
  transaction. The Reports button triggers this job directly via the
  Jobs API.

- **Pattern B — [Lakehouse Sync](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync) (native Lakebase CDC, Beta):**
  Use Lakebase's built-in Lakehouse Sync to continuously replicate the
  staging tables into UC-managed Delta tables (`lb_<table>_history`) as
  **SCD Type 2** — every insert / update / delete is appended as a new
  row with `_change_type`, `_timestamp`, `_lsn`, `_xid` system columns.
  Replication itself needs **no external compute, pipeline, or job**;
  it's a native Lakebase feature powered by the `wal2delta` Postgres
  extension.


Then wire the job into the app (same surface for both patterns):

- `POST /api/jobs/run-forward-etl` (SP client) — triggers the job
  (Pattern A: the MERGE job; Pattern B: the dedup-into-gold job)
- `GET  /api/jobs/{run_id}` — polls run status
- `Reports.tsx` — "Run forward-ETL" button + status indicator + a
  recent-runs table

**Files:** `lakebase/forward_etl/...`, `app/backend/routers/jobs.py`,
`app/frontend/src/pages/Reports.tsx`

**Docs:**
- Lakehouse Sync (Pattern B reference): https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync
- Lakebase + Apps integration: https://docs.databricks.com/aws/en/oltp/projects/databricks-apps

**Done when:**
- [ ] Triggering the job from the Reports page produces a successful run
- [ ] Re-running with no new staging rows is a no-op (Pattern A:
      `processed=false` filter; Pattern B: dedup CTAS/MERGE is
      naturally idempotent)
- [ ] `gold.customer_notes` rowcount equals the expected unique-note
      count in staging (Pattern A: rows with `processed=true`;
      Pattern B: distinct PKs surviving dedup of `lb_*_history`)

---

## T8 — Deploy via DABs as a git-source app

**Why:** The production pattern for Apps is **git-source apps** declared
via DABs and deployed by **GitHub Actions on push / release**. Manual
`databricks apps deploy` from a laptop is fine for inner-loop dev but
isn't reviewable, doesn't scale, and ties the app to whoever ran the
command. **For this capstone the deployed app must be a git-source app**
— i.e. the DABs `app` resource declares the GitHub repo + branch and
Databricks pulls the source from there. Source-code-path-only apps that
upload a workspace folder are explicitly **not** accepted for the
submission.

**Do this:**

- `databricks.yml` — bundle root with `targets: dev / prod`, project
  name, default workspace host, and `variables:` for `warehouse_id`,
  `lakebase_instance`, `dashboard_id`, `genie_space_id`, `secret_scope`.
- `resources/app.yml` — define the app as a **git-source app**. The
  required fields are `git_repository.url`, `git_source.branch`, and
  `git_source.source_code_path` (path to the app inside the repo). You
  still keep `source_code_path` for the local bundle reference. Example
  shape (check the [resource reference][1] for any field renames in your
  CLI version):
  ```yaml
  resources:
    apps:
      customer360:
        name: customer360
        description: Customer 360 capstone app
        source_code_path: ./app           # local path inside the bundle
        git_repository:
          url: https://github.com/<YOU>/<REPO>
        git_source:
          branch: main
          source_code_path: app           # path inside the repo
        resources:
          - name: warehouse
            sql_warehouse: { id: ${var.warehouse_id} }
          - name: lakebase
            postgres:
              database: ${var.lakebase_database}
              permission: CAN_CONNECT_AND_CREATE
          - name: dashboard
            dashboard: { id: ${var.dashboard_id} }
          - name: genie_space
            genie_space: { id: ${var.genie_space_id} }
          - name: secrets
            secret: { scope: ${var.secret_scope} }
        user_api_scopes:
          - sql
          - dashboards.genie
          - dashboards
          - iam.access-control:read
  ```
  > Requires Databricks CLI ≥ 0.290.0 for `git_repository` /
  > `git_source` on app resources.
- `resources/jobs.yml` — define the forward-ETL job from T7.
- `resources/lakebase.yml` — declarative synced-table specs (the YAML
  equivalent of T1's psycopg DDL), so the synced tables are also part
  of the bundle and not drift from manual creation.
- `.github/workflows/deploy.yml` — on push to `main` (or on release
  tag, see the cookbook for the recommended split):
  1. `databricks bundle validate --target prod`
  2. `databricks bundle deploy --target prod`
  3. `databricks bundle run customer360 --target prod`
     (this is what triggers the actual code pull from your git ref +
     restarts the app)

  Auth via OAuth M2M, not PAT — set repo secrets
  `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`
  for a service principal that has access to the prod workspace.

[1]: https://docs.databricks.com/aws/en/dev-tools/bundles/resources#app

**Files:** `databricks.yml`, `resources/app.yml`, `resources/jobs.yml`,
`resources/lakebase.yml`, `.github/workflows/deploy.yml`

**Docs:**
- DABs for Apps tutorial: https://docs.databricks.com/aws/en/dev-tools/bundles/apps-tutorial
- DABs Apps resource reference (incl. `git_repository` / `git_source`): https://docs.databricks.com/aws/en/dev-tools/bundles/resources#app
- Git-source apps overview: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/git
- CI/CD with bundles + GitHub Actions: https://docs.databricks.com/aws/en/dev-tools/bundles/ci-cd-bundles

**Cookbook:** https://apps-cookbook.dev/blog/automate-apps-deployments-dabs

**Done when:**
- [ ] `databricks bundle validate --target prod` passes
- [ ] In the workspace UI, the deployed app's source shows the **git
      repository + branch** (not a workspace folder upload)
- [ ] A push to `main` produces a green GHA run, and the deployed app
      restarts on the new commit (verify the commit SHA on the app's
      Deployments tab matches `HEAD` of `main`)

---

## T9 — Lakebase ops

| # | Task | What to do | Skill |
|---|---|---|---|
| **T9a** | Branch + PITR | Create a child branch from `capstone-pg`. On the branch, `DELETE FROM customer_notes_staging` (destructive). On the parent, restore to a timestamp before the delete. Capture screenshots of branch creation and the post-restore row count. | Branching + PITR |
| **T9b** | Query insights | Run `SELECT … WHERE actor_email = '…'` against `customer_audit_log` 100×. Open Query Performance (or `pg_stat_statements`) — the query is slow because there's no index. `CREATE INDEX ON customer_audit_log (actor_email)`. Re-run; record before/after p95 latency. | Query perf |

**Docs:**
- Branches: https://docs.databricks.com/aws/en/oltp/projects/branches
- PITR: https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore
- Query Performance UI: https://docs.databricks.com/aws/en/oltp/projects/query-performance
- pg_stat_statements: https://docs.databricks.com/aws/en/oltp/projects/pg-stat-statements

**Done when:**
- [ ] Screenshots of branch creation, PITR restore, and before/after p95 latency

---

## Optimizations & engineering hygiene

Reviewers will look for a real production-grade React + FastAPI app, not
a demo script. Address these patterns explicitly — call them out in your
submission writeup.

### Pagination (server-side, always)

- List endpoints accept `page` + `page_size` (or a cursor) and return
  `{ items, total, page, page_size }`. Never load 10k rows in one
  response.
- Default `page_size = 25`, hard cap at `100`. Reject larger values with
  `422`.
- Add a Lakebase index on the columns you sort/filter by (e.g. composite
  on `segment_id, lifetime_value DESC`); without it `OFFSET` over a
  large dataset gets slow fast.
- Prefer **keyset pagination** (`WHERE lifetime_value < :last_seen ...
  ORDER BY lifetime_value DESC LIMIT 25`) over `OFFSET` once the dataset
  grows beyond a few thousand rows.

### Caching

- **Server-side:** cache `/api/config`, the segments list, and the
  products list (rarely change) with `cachetools.TTLCache` or
  `fastapi-cache` — TTL ~5 min. Don't cache per-customer payloads on
  the server (cardinality explosion).
- **Client-side (per user session):** wrap all GETs in **TanStack Query
  (React Query)** with per-key `staleTime`. Suggested defaults:
  - Customer list: `staleTime: 10s`, `gcTime: 5m`
  - Customer detail: `staleTime: 30s`
  - Customer metrics: `staleTime: 60s` (expensive query, slow-changing)
  - Config / segments / products: `staleTime: 5m`
  Use `queryClient.invalidateQueries(['customer', id])` after a write so
  the UI re-fetches automatically (optimistic updates make this feel
  instant).
- **Browser:** set `Cache-Control: private, max-age=…, must-revalidate`
  on idempotent GETs so back-button navigation is free.

### Connection pooling (Lakebase)

- Use `psycopg_pool.AsyncConnectionPool` (size 2–10) per worker. Without
  pooling you pay TLS + auth on every request.
- Lakebase OAuth tokens expire (~1h). Either (a) set the pool's
  `reconnect_failed=True` and supply a fresh token via `connection_factory`
  on every checkout, or (b) recreate the pool on token refresh. Either
  is fine; document which you chose.

### React performance

- Code-split routes with `React.lazy` + `<Suspense>` so the initial
  bundle stays small.
- Memoize the list grid (`React.memo` + stable `key`); use the MUI
  DataGrid's built-in virtualization (don't roll your own).
- Debounce filter inputs (~250ms) before triggering a refetch.
- Fan-out independent fetches in parallel (`useQueries`,
  `Promise.all`) — the detail page should kick off Profile + Metrics +
  Activity + Notes in one round-trip's worth of latency, not four.

### API hygiene

- Enable `gzip` / `br` compression in FastAPI (`GZipMiddleware`,
  `minimum_size=1000`).
- Return the minimum payload — don't `SELECT *` if the UI only needs
  6 fields.
- Use Pydantic response models so the schema is enforced and documented
  in OpenAPI.
- Set sensible timeouts on outbound calls (warehouse, Lakebase, Genie)
  so a slow downstream doesn't tie up an app worker.

### Observability

- Structured logging (`logging.getLogger(__name__)` + JSON formatter).
- Per-request `X-Request-Id` header (generate if missing) echoed back
  for correlation across the React → FastAPI → Lakebase / SQL hop.
- Log slow queries (Lakebase / SQL warehouse) with their parameters at
  `WARNING` level when they exceed a threshold (e.g. 500ms).

**Done when:**
- [ ] Customer list endpoint serves any page in < 200ms server-side
      (cold cache, warehouse not involved).
- [ ] Detail page renders to first paint in < 800ms with cache warm.
- [ ] React Query devtools show cache hits on tab switches and
      back-navigation.
- [ ] No N+1 Lakebase queries on the detail page (verify in logs).
- [ ] Writeup explicitly calls out the caching, pagination, and pooling
      choices you made.

---

## Submission

- [ ] Every task above checked
- [ ] Repo URL with green main CI
- [ ] Live app URL (deployed as a **git-source app** via DABs)
- [ ] 3-min screen recording: customer list → detail (all tabs) → add
      note → override segment → genie → dashboard → run forward-ETL
- [ ] Output from `examples/m2m_test.py` and `examples/u2m_test.py` (T3) pasted in your writeup, showing both auth flows return `200` + customer JSON
- [ ] T9 screenshots (branch + PITR, before/after p95 latency)
- [ ] One-paragraph reflection: which sync mode you chose for each
      synced table and why, plus which optimizations you implemented
      and which you'd add next

## Skills coverage map

| Skill | Tested by |
|---|---|
| Lakebase synced tables (sync mode choice) | T1 + reflection |
| Lakebase psycopg + DDL | T1, T3 (notes / override writes), T6 (env wiring) |
| Lakebase synced reads | T3 (List + Detail) |
| Lakebase CRUD + audit | T3 (notes + segment override) |
| OBO + SP authentication | T2 |
| OAuth scopes + `user_authorization` | T6 |
| SQL warehouse from an App | T3 (Metrics) |
| External M2M / U2M auth | T3 (External) |
| Lakeview dashboard embed | T4 |
| Genie Conversation API | T5 |
| Forward ETL | T7 |
| DABs + git-source app + GitHub Actions CI/CD | T8 |
| Lakebase branching, PITR, query perf | T9 |
| React + FastAPI app engineering (caching, pagination, pooling, theming) | App design + Optimizations |
