# Capstone tasks

Work top-to-bottom. Each task names the file(s) to create/edit and the skill it tests.

## Prerequisites

- Databricks workspace access (Unity Catalog enabled, can create Lakebase + apps).
- A Serverless SQL warehouse you can use.
- `databricks` CLI ≥ 0.299, `uv`, `node` ≥ 20.
- Forked this scaffold into your own repo (private is fine).

The notebook references throughout this doc point at the public installer
repo on GitHub. Open them in your browser for source you can adapt:

> `https://github.com/jnshubham/gdc-apps-lakebase-capstone/blob/main/capstone/notebooks/<filename>.py`

---

## Phase 0 — Setup

The `curl ... | bash` installer (see the repo root README) ran notebooks
**01, 02, 04, 05** in your workspace and wrote `app/.env`.

**Notebook 03 (synced + staging tables) is your job.** It is the reference
for tasks **T2–T5** below; you will run it (or write your own equivalent)
yourself.

| # | Notebook | Run by | What it gives you |
|---|---|---|---|
| 01 | `01_generate_gold_data.py` | installer | 5 gold Delta tables in `<catalog>.gold.*` |
| 02 | `02_create_lakebase_instance.py` | installer | `PGHOST`, `PGDATABASE`, `SECRET_SCOPE` |
| 03 | `03_create_synced_and_staging.py` | **you** | 3 synced tables + 3 staging tables |
| 04 | `04_create_aibi_dashboard.py` | installer | `DASHBOARD_ID` |
| 05 | `05_create_genie_space.py` | installer | `GENIE_SPACE_ID` |

- [ ] Installer ran cleanly; `app/.env` exists with all IDs.
- [ ] You ran `03_create_synced_and_staging.py` yourself (or wrote the
  equivalent declaratively under `lakebase/reverse_etl/`).
- [ ] `databricks.yml` `variables` filled in (`warehouse_id`,
  `genie_space_id`, `dashboard_id`).

---

## Phase 1 — Auth + connections

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T1** | Implement `obo_client(request)` and `sp_client()`. Reads `X-Forwarded-Access-Token`. | `app/backend/auth.py` | OBO + SP auth |
| **T2** | Implement `lakebase_obo()` and `lakebase_sp()` context managers (psycopg). Reference notebook 03 for the synced-table setup this connects to. | `app/backend/db.py` | Lakebase connection |

- [ ] T1 — `/api/health` returns 200 when called from the deployed app shell.
- [ ] T2 — a quick endpoint that runs `SELECT 1` against Lakebase using OBO works.

---

## Phase 2 — Read paths (SQL warehouse + synced Lakebase)

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T3** | `GET /api/customers` (filters: segment, min_ltv, max_churn) — query SQL warehouse via OBO. Render in a DataGrid. | `app/backend/routers/customers.py`, `app/backend/routers/analytics.py`, `app/frontend/src/pages/Customers.tsx` | SQL warehouse + OBO |
| **T4** | `GET /api/customers/{id}` — read from `customers_synced` + last 20 from `transactions_synced`. Implement profile tab. | `app/backend/routers/customers.py`, `app/frontend/src/pages/CustomerDetail.tsx` | Lakebase synced + OBO |

- [ ] Customer list + filters work.
- [ ] Customer detail shows profile + recent activity.

---

## Phase 3 — Write paths (Lakebase CRUD + audit)

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T5** | Notes CRUD + segment override write to `*_staging`, append a `customer_audit_log` row in the same transaction. Reference notebook 03 for the staging-table DDL. | `app/backend/routers/customers.py`, `app/frontend/src/pages/CustomerDetail.tsx` | Lakebase CRUD |

- [ ] Adding a note appears immediately in the list.
- [ ] An audit row exists in `customer_audit_log` for every write.

---

## Phase 4 — Genie + dashboard embed

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T6** | Genie Conversation API — start, send, get message. OBO. Implement chat UI. | `app/backend/routers/genie.py`, `app/frontend/src/pages/Genie.tsx` | Genie OBO |
| **T7** | Embed the Lakeview dashboard in an iframe. Add a `/api/config` endpoint that returns `dashboard_id` + `databricks_host`. | `app/frontend/src/pages/Dashboard.tsx`, `app/backend/main.py` | Dashboard embed |

- [ ] Asking "top segment by LTV" returns an answer + result preview.
- [ ] Dashboard renders inside the app.

---

## Phase 5 — Job triggering + external API

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T8** | "Run forward-ETL" button → `POST /api/jobs/run-forward-etl` (SP) → poll status. | `app/backend/routers/jobs.py`, `app/frontend/src/pages/Reports.tsx` | Jobs API + SP |
| **T9** | `/api/external/*` endpoints — accept both U2M (user PAT) and M2M (SP OAuth client-credentials). Document curl examples for both auth modes. | `app/backend/routers/external.py` | M2M + U2M |

- [ ] Triggering the job from the UI produces a run that succeeds.
- [ ] Both M2M and U2M curl invocations return data; outputs captured in your writeup.

---

## Phase 6 — DABs + CI/CD

| # | Task | File(s) to create | Skill |
|---|---|---|---|
| **T10** | Wire all five resources (lakebase, warehouse, job, genie, dashboard) in `resources/`. `databricks bundle validate` passes. | `resources/app.yml`, `resources/jobs.yml`, `resources/lakebase.yml`, `databricks.yml` | DABs |
| **T11** | Create the GitHub Actions workflow yourself. Set GitHub secrets `DATABRICKS_HOST` + `DATABRICKS_TOKEN`. Push to main → workflow deploys + restarts the app. Optionally switch to `git_repository` mode. | `.github/workflows/deploy.yml` | Git-backed Apps + CI/CD |

- [ ] `databricks bundle validate` passes.
- [ ] A push to main results in a successful GHA run.

---

## Phase 7 — Forward ETL

| # | Task | What to build | Skill |
|---|---|---|---|
| **T12** | Pick **one** of two patterns and implement it under `lakebase/forward_etl/`: (a) a psycopg notebook job that reads staging rows where `processed=false`, MERGEs into Delta, then flips `processed=true`; or (b) a Lakeflow Declarative Pipeline that does the same. Re-run produces no duplicates. After running, `gold.customer_notes` rowcount equals the staging rowcount where `processed=true`. | Forward ETL |

- [ ] Successful run from Jobs UI.
- [ ] Re-running with no new data is a no-op.

---

## Phase 8 — Lakebase ops

| # | Task | What to do | Skill |
|---|---|---|---|
| **T13** | **Branch + PITR.** Create a child branch from `capstone-pg`. On the branch, `DELETE FROM customer_notes_staging` (destructive). Then on the parent, restore to a timestamp before the delete. Capture screenshots of both. | Branching + PITR |
| **T14** | **Query insights.** Run `SELECT … WHERE author_email = '…'` against `customer_audit_log` 100×. Open Lakebase Query Insights (or `pg_stat_statements`) — it will be slow. Add `CREATE INDEX ON customer_audit_log (actor_email)`. Re-run. Record before/after p95 latency. | Query perf tuning |

- [ ] Screenshots of branch creation, PITR restore, and query-insights before/after.

---

## Submission checklist

- [ ] All tasks above checked.
- [ ] Repo URL (with `.github/workflows/deploy.yml` green on main).
- [ ] App URL (running, deployed via DABs).
- [ ] 3-minute screen recording walking through customer list → detail → notes → genie → dashboard → run-job.
- [ ] M2M + U2M curl outputs pasted in your writeup.
- [ ] Branching + PITR + query-perf screenshots.
- [ ] One-paragraph reflection: which sync mode you chose for each synced table and why.

## Skills coverage map

| Skill from training | Tested by |
|---|---|
| Apps overview / supported frameworks | T11 (deployed React+FastAPI) |
| Lakebase intro / instance creation | Notebook 02 |
| Connect to SQL warehouse | T3 |
| Resources: warehouse, lakebase, secrets, serving endpoints | `resources/app.yml` (T10) |
| OAuth / OIDC user auth | T1, T6, T9 |
| Deploy from Git | T11 |
| Compute sizing / lifecycle | `app.yaml` notes + DABs |
| Branching, PITR, perf | T13, T14 |
| Lakebase + UC governance | Notebook 02 (UC catalog) + T3 federated query |
| UC federated queries | T3 (joins gold + Lakebase via UC) |
| Apps + Lakebase CRUD | T5 |
| Apps + Genie | T6 |
| Apps + Analytics + Dashboards | T7 |
| CI/CD via DABs | T10, T11 |
| Forward / reverse ETL | Notebook 03 (you), T12 |
| Sync mode choice | written reflection in submission |
| External M2M / U2M | T9 |
