# T7 — Forward ETL: staging → gold (Pattern A) — Design Spec

**Goal:** Drain the app's Lakebase staging writes (notes + segment overrides)
back into Delta gold, triggered on demand from the Reports page and executed
as a serverless Databricks notebook job.

**Pattern:** A — psycopg + `MERGE INTO` Delta (pull, on-demand). Chosen over
Pattern B (Lakehouse Sync CDC) because T1 already built the `processed` flags
and partial indexes this pattern consumes, it avoids a Beta feature, and it
directly demonstrates the transactional-MERGE + idempotency the rubric checks.

---

## Architecture & data flow

An on-demand **pull drain**. The Reports page triggers a serverless notebook
job via the Jobs API (as the SP). For each staging table the job:

1. Connects to Lakebase via psycopg as the job's run-as identity (fresh OAuth
   token, `sslmode=require`).
2. Snapshots the **unprocessed row IDs** (`WHERE processed = false`).
3. Builds a Spark DataFrame from those rows and **`MERGE INTO`** the gold
   target, keyed on the natural PK (idempotent upsert).
4. **Only after** the MERGE succeeds: `UPDATE ... SET processed = true,
   processed_at = NOW() WHERE <pk> = ANY(ids)` for the snapshotted ID set.

### Crash safety — "same transaction" is impossible across systems

The spec's "in the same transaction" cannot be literal: the MERGE runs on
Spark/Delta and the flag flip runs on Postgres/Lakebase — two separate systems
with no shared transaction. The safe ordering is **MERGE first, then flip by
ID set**:

- **Delta is the source of truth.** The `processed` flag is best-effort
  catch-up.
- A crash **after** MERGE but **before** the flip re-MERGEs those exact rows
  next run. Because the MERGE keys on the PK, this is a harmless no-op — no
  duplicates, no data loss.
- The reverse order (flip first) could silently lose rows on a crash, so it is
  rejected.

This reasoning is documented in the notebook header and the submission writeup.

### Gold targets

Both created `CREATE TABLE IF NOT EXISTS` by the notebook (self-contained on
first run), in `<catalog>.gold`:

| Gold table | Source staging | MERGE key | Shape |
|---|---|---|---|
| `customer_notes` | `customer_notes_staging` | `note_id` | append-style |
| `customer_segment_overrides` | `customer_segment_overrides_staging` | `customer_id` | one row per customer |

`customer_audit_log` is **not** drained — it is an in-Lakebase audit trail, not
a gold target.

---

## Components

### 1. Notebook job

**File:** `capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging.py`
(`# Databricks notebook source` format).

- Gold DDL (`CREATE TABLE IF NOT EXISTS` for both targets) at the top.
- One `drain(table, pk, gold_table, select_cols, merge_on)` function, called
  once per staging table, implementing snapshot → MERGE → flip as above.
- No-op fast path: `if not rows: return 0` before touching Spark.
- MERGE: `WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *`.
- Flip: `UPDATE {table} SET processed=true, processed_at=NOW() WHERE {pk} = ANY(%s)`.
- Connection: mints token via `WorkspaceClient().config.oauth_token()` (job
  run-as identity), connects with psycopg + `sslmode=require`. PGHOST /
  PGDATABASE from the notebook's env (job env or `.env` fallback for local
  runs).
- Output: prints per-table counts (`notes drained: N`, `overrides drained: M`).
  This is the evidence for the rowcount "Done when" check.

### 2. Backend router `jobs.py`

**File:** `capstone-app/app/backend/routers/jobs.py`,
`router = APIRouter(prefix="/api/jobs", tags=["jobs"])`, registered in
`main.py`. All endpoints use the existing `Sp` dependency (SP client) — this is
background work, not user-attributed. SDK calls (sync) run in
`asyncio.to_thread`.

Config: add `forward_etl_job_id: str | None = None` to `Settings` (from the
bundle-injected `FORWARD_ETL_JOB_ID` env var). If unset, all three endpoints
return `503 forward-ETL job not configured`.

| Endpoint | SDK call | Returns |
|---|---|---|
| `POST /api/jobs/run-forward-etl` | `jobs.run_now(job_id)` | `RunTrigger {run_id}` |
| `GET /api/jobs/runs/{run_id}` | `jobs.get_run(run_id)` | `RunStatus` |
| `GET /api/jobs/runs` | `jobs.list_runs(job_id, limit=10)` | `list[RunSummary]` |

Pydantic response models in `models.py`:
- `RunTrigger { run_id: int }`
- `RunStatus { run_id, state, result_state, start_time, duration_ms, run_page_url }`
- `RunSummary { run_id, state, result_state, start_time, duration_ms }`

`state` normalized from the SDK `RunState` (`life_cycle_state`), `result_state`
from `RunState.result_state`. No server-side polling loop — the client polls
`GET /runs/{run_id}` (the T5 idiom).

### 3. Frontend

**`lib/types.ts`** — add `RunTrigger`, `RunStatus`, `RunSummary`.

**`lib/api.ts`** — add a `jobs` namespace:
```ts
jobs: {
  runForwardEtl: () => request<RunTrigger>("/jobs/run-forward-etl", { method: "POST" }),
  getRun: (runId: number) => request<RunStatus>(`/jobs/runs/${runId}`),
  listRuns: () => request<RunSummary[]>("/jobs/runs"),
}
```

**`lib/queries.ts`** — `useForwardEtlRuns()` (list, `staleTime: 5s`),
`useRunForwardEtl()` mutation. On trigger success capture `run_id` and poll the
active run via `useQuery` with `refetchInterval` while the state is
non-terminal; on a terminal state `invalidateQueries(["jobs","runs"])` so the
history refreshes.

**`pages/Reports.tsx`** — cockpit-styled to match the app idiom:
- "Run forward-ETL" button, disabled while a run is in flight.
- Live status indicator (`PENDING`/`RUNNING`/`SUCCESS`/`FAILED`) using the
  green/amber/alert tone vocabulary.
- Recent-runs table: run_id, state (colored), started, duration, "workspace"
  deep-link (`run_page_url`). Loading/empty/error via the existing `states`
  components.

**`main.tsx`** — replace the `ComingSoon` at `path: "reports"` with `<Reports />`
(lazy + Suspense, matching the other routes).

### 4. DABs wiring (closes the T8 deferral)

**`resources/jobs.yml`** (new):
```yaml
resources:
  jobs:
    forward_etl:
      name: "customer360 forward-ETL (${bundle.target})"
      tasks:
        - task_key: drain_staging
          notebook_task:
            notebook_path: ../capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging
          environment_key: default
      environments:
        - environment_key: default
          spec:
            client: "3"
            dependencies: ["psycopg[binary]", "databricks-sdk"]
```

**`resources/app.yml`** — add to the app's `resources` block:
```yaml
- name: forward-etl-job
  job:
    id: ${resources.jobs.forward_etl.id}
    permission: "CAN_MANAGE_RUN"
```

**`app/app.yaml`** — wire the env var:
```yaml
- name: FORWARD_ETL_JOB_ID
  valueFrom: forward-etl-job
```

Loop: bundle creates the job → binds it to the app → injects the ID →
`jobs.py` triggers it.

### 5. Run-as Lakebase grants (prerequisite)

The job's run-as identity needs Lakebase access to the staging tables:
- **Dev:** runs as the deploying user (project owner) — already has access.
- **Prod:** runs as the bundle's run-as SP — needs `SELECT`/`UPDATE` on the two
  staging tables and `USAGE` on the schema, the same grants
  `grant_app_sp.py` applies to the app SP.

Captured as an explicit prerequisite: if the prod job SP differs from the app
SP, run the grant step against the job SP too. The gold-side writes (MERGE) run
through Spark/UC under the job's identity and need `USE CATALOG` + `USE SCHEMA`
+ `MODIFY` on `<catalog>.gold` (the project owner already has this; document for
prod).

---

## Testing

- **Notebook (manual, live):** run `drain_staging` once with unprocessed rows
  present → gold tables created, rows merged, counts printed, staging flags
  flipped. Run again immediately → both counts 0 (no-op), no new gold rows.
- **Router (pytest):** unit tests with `app.dependency_overrides[get_sp_client]`
  returning a stub WorkspaceClient; assert `run_now`/`get_run`/`list_runs` are
  called with the configured job id and the response shape maps correctly.
  Assert `503` when `forward_etl_job_id` is unset. These follow the existing
  `Sp`-override test pattern; no live Databricks needed.
- **Frontend:** `bunx tsc --noEmit` + `bun run build` clean.

## Done when (from CAPSTONE_TASKS.md T7)

- [ ] Triggering the job from the Reports page produces a successful run.
- [ ] Re-running with no new staging rows is a no-op (`processed=false` filter).
- [ ] `gold.customer_notes` rowcount equals the expected unique-note count in
      staging (rows with `processed=true`).

## Out of scope

- Pattern B (Lakehouse Sync / CDC).
- Draining `customer_audit_log` to gold.
- Scheduling the job (on-demand trigger only, per the Reports button).
