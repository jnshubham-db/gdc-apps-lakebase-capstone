# T7 — Forward ETL: staging → gold (Pattern A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drain the app's Lakebase staging writes (notes + segment overrides) back into Delta gold, triggered on demand from the Reports page and executed as a serverless Databricks notebook job.

**Architecture:** A serverless notebook job (Pattern A) reads unprocessed staging rows via psycopg, `MERGE`s them into gold via Spark, then flips `processed=true` for that exact ID set (MERGE-first, Delta as source of truth — crash between steps re-MERGEs harmlessly). A FastAPI `jobs` router triggers/polls the job via the Jobs SDK as the SP; a React Reports page drives it. DABs wiring (`resources/jobs.yml` + app `job` binding + `FORWARD_ETL_JOB_ID` env) closes the loop deferred from T8.

**Tech Stack:** FastAPI, Databricks SDK (Jobs), psycopg, Spark/Delta, Pydantic, React + TanStack Query + TypeScript, Recharts-adjacent cockpit UI, DABs.

## Global Constraints

- Python: ruff-clean (`uvx ruff format app/ lakebase/` + `uvx ruff check --fix app/ lakebase/`), `line-length = 100`, `target-version = py311`. Both must pass before every commit.
- Pytest runs from `app/`; `live`-marked tests skip without Databricks auth. Test command: `cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest -q`.
- Frontend must pass `bunx tsc --noEmit` and `bun run build` (run from `app/frontend/`) before commit. Vite `outDir` is `app/backend/static/`.
- ETL pattern is **A** (psycopg + MERGE). Never build Pattern B.
- Ordering is **MERGE first, then flip `processed`** by snapshotted ID set. Never flip first.
- Gold targets: `<catalog>.gold.customer_notes` (MERGE key `note_id`), `<catalog>.gold.customer_segment_overrides` (MERGE key `customer_id`). `customer_audit_log` is never drained.
- SP identity for all `jobs.py` endpoints (existing `Sp` dependency). No user-attribution.
- No server-side polling loop; the client polls `GET /runs/{run_id}` (the T5 idiom).
- Job ID reaches the app via bundle-injected `FORWARD_ETL_JOB_ID` (app `job` resource binding + `valueFrom`), never hardcoded.
- Catalog var everywhere is `test_jg_catalog`; gold schema is `gold`.

---

## File Structure

- **Create** `capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging.py` — the notebook job (self-contained: gold DDL + drain).
- **Create** `capstone-app/lakebase/forward_etl/README.md` — pattern rationale + run/idempotency notes.
- **Create** `capstone-app/app/backend/routers/jobs.py` — three Jobs-API endpoints (SP).
- **Modify** `capstone-app/app/backend/models.py` — add `RunTrigger`, `RunStatus`, `RunSummary`.
- **Modify** `capstone-app/app/backend/config.py` — add `forward_etl_job_id`.
- **Modify** `capstone-app/app/backend/main.py` — register `jobs.router`.
- **Create** `capstone-app/app/tests/test_t7_jobs.py` — router tests (stub SP client).
- **Modify** `capstone-app/app/frontend/src/lib/types.ts` — add run types.
- **Modify** `capstone-app/app/frontend/src/lib/api.ts` — add `jobs` namespace.
- **Modify** `capstone-app/app/frontend/src/lib/queries.ts` — add run hooks.
- **Create** `capstone-app/app/frontend/src/pages/Reports.tsx` — the Reports page.
- **Modify** `capstone-app/app/frontend/src/main.tsx` — route `reports` → `<Reports />`.
- **Create** `resources/jobs.yml` (repo root) — forward-ETL job resource.
- **Modify** `resources/app.yml` (repo root) — add `forward-etl-job` app resource.
- **Modify** `capstone-app/app/app.yaml` — add `FORWARD_ETL_JOB_ID` via `valueFrom`.

---

## Task 1: Notebook job — `drain_staging.py`

Self-contained serverless notebook: create gold tables if missing, then drain both staging tables (snapshot → MERGE → flip). No pytest (Spark/Lakebase runtime only); verified by ruff + a live manual run described at the end.

**Files:**
- Create: `capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging.py`
- Create: `capstone-app/lakebase/forward_etl/README.md`

**Interfaces:**
- Consumes: Lakebase staging tables from T1 — `customer_notes_staging (note_id UUID PK, customer_id, author_email, note_text, created_at, processed, processed_at)`, `customer_segment_overrides_staging (override_id UUID PK, customer_id UNIQUE, override_segment, reason, author_email, created_at, updated_at, processed, processed_at)`. Env `PGHOST`, `PGDATABASE`, `CAPSTONE_CATALOG`.
- Produces: gold tables `<catalog>.gold.customer_notes`, `<catalog>.gold.customer_segment_overrides`. Prints `notes drained: N`, `overrides drained: M` to run output.

- [ ] **Step 1: Write the notebook**

Create `capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging.py`:

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Forward ETL (Pattern A) — drain Lakebase staging into Delta gold
# MAGIC
# MAGIC Reads unprocessed rows from the app's Lakebase staging tables, MERGEs
# MAGIC them into gold, then flips `processed=true` for that exact ID set.
# MAGIC
# MAGIC **Ordering is MERGE-first, flip-after.** True cross-system atomicity is
# MAGIC impossible (Spark/Delta vs Postgres/Lakebase are separate systems). Delta
# MAGIC is the source of truth; a crash between MERGE and flip re-MERGEs the same
# MAGIC rows next run — harmless because the MERGE keys on the PK. The reverse
# MAGIC order could silently lose rows, so it is never used.

# COMMAND ----------

import os

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row

CATALOG = os.environ["CAPSTONE_CATALOG"]
GOLD = f"{CATALOG}.gold"

# COMMAND ----------

# MAGIC %md ## Gold DDL — self-contained on first run

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.customer_notes (
    note_id       STRING,
    customer_id   STRING,
    author_email  STRING,
    note_text     STRING,
    created_at    TIMESTAMP
) USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.customer_segment_overrides (
    customer_id      STRING,
    override_segment STRING,
    reason           STRING,
    author_email     STRING,
    updated_at       TIMESTAMP
) USING DELTA
""")

# COMMAND ----------

# MAGIC %md ## Lakebase connection (SP OAuth token, sslmode=require)

# COMMAND ----------

def lakebase_conn() -> psycopg.Connection:
    """psycopg connection as the job run-as identity (fresh OAuth token)."""
    w = WorkspaceClient()
    token = w.config.oauth_token().access_token
    user = w.current_user.me().user_name
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ["PGDATABASE"],
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )

# COMMAND ----------

# MAGIC %md ## Drain — snapshot → MERGE → flip

# COMMAND ----------

def drain(conn, *, table, pk, gold_table, select_cols, merge_on, cast) -> int:
    """Drain one staging table into its gold target. Returns rows drained."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {select_cols} FROM {table} WHERE processed = false")
        rows = cur.fetchall()
    if not rows:
        return 0

    ids = [r[pk] for r in rows]
    # UUID/JSON → strings so Spark can infer a clean schema.
    df = spark.createDataFrame([cast(r) for r in rows])
    view = f"_stage_{table}"
    df.createOrReplaceTempView(view)
    spark.sql(f"""
        MERGE INTO {gold_table} t USING {view} s ON {merge_on}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    # Flip only AFTER the MERGE committed, for the exact snapshotted id set.
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET processed = true, processed_at = NOW() "
            f"WHERE {pk} = ANY(%s)",
            ([str(i) for i in ids],),
        )
    conn.commit()
    return len(ids)

# COMMAND ----------

def _cast_note(r: dict) -> dict:
    return {
        "note_id": str(r["note_id"]),
        "customer_id": r["customer_id"],
        "author_email": r["author_email"],
        "note_text": r["note_text"],
        "created_at": r["created_at"],
    }

def _cast_override(r: dict) -> dict:
    return {
        "customer_id": r["customer_id"],
        "override_segment": r["override_segment"],
        "reason": r["reason"],
        "author_email": r["author_email"],
        "updated_at": r["updated_at"],
    }

# COMMAND ----------

with lakebase_conn() as conn:
    n_notes = drain(
        conn,
        table="customer_notes_staging",
        pk="note_id",
        gold_table=f"{GOLD}.customer_notes",
        select_cols="note_id, customer_id, author_email, note_text, created_at",
        merge_on="t.note_id = s.note_id",
        cast=_cast_note,
    )
    n_over = drain(
        conn,
        table="customer_segment_overrides_staging",
        pk="override_id",
        gold_table=f"{GOLD}.customer_segment_overrides",
        select_cols=(
            "override_id, customer_id, override_segment, reason, "
            "author_email, updated_at"
        ),
        merge_on="t.customer_id = s.customer_id",
        cast=_cast_override,
    )

print(f"notes drained: {n_notes}")
print(f"overrides drained: {n_over}")
```

Note: the overrides MERGE keys on `customer_id` (one active override per customer) while the snapshot/flip key is the PK `override_id` — this is deliberate and correct: gold holds the latest override per customer, staging flags each processed row by its own id.

- [ ] **Step 2: Write the README**

Create `capstone-app/lakebase/forward_etl/README.md`:

```markdown
# T7 — Forward ETL: staging → gold (Pattern A)

Drains the app's Lakebase staging writes back into Delta gold, on demand.

## Pattern A — psycopg + MERGE INTO (pull, on-demand)

`pattern_a_psycopg2/drain_staging.py` is a serverless notebook job. For each
staging table it: (1) snapshots unprocessed rows (`WHERE processed = false`)
via psycopg as the job SP; (2) MERGEs them into gold via Spark (idempotent on
the key); (3) flips `processed = true` for that exact id set — **only after**
the MERGE commits.

### Why MERGE-first (crash safety)

Delta and Postgres are separate systems; there is no shared transaction. Delta
is the source of truth and the `processed` flag is best-effort catch-up. A
crash after MERGE but before the flip re-MERGEs those rows next run — harmless,
because the MERGE keys on the PK (no duplicates, no loss). Flipping first could
silently lose rows, so it is never done.

### Gold targets

| Gold table | Source staging | MERGE key |
|---|---|---|
| `customer_notes` | `customer_notes_staging` | `note_id` |
| `customer_segment_overrides` | `customer_segment_overrides_staging` | `customer_id` |

`customer_audit_log` is an in-Lakebase audit trail and is never drained.

### Idempotency

Re-running with no new staging rows drains 0 rows and MERGEs nothing (the
`processed = false` filter empties the snapshot). Re-running after a partial
failure re-MERGEs the same keys — same gold result.

### Run-as grants (prod)

In dev the job runs as the project owner (already has access). In prod it runs
as the bundle run-as SP, which needs `SELECT`/`UPDATE` on the two staging
tables + `USAGE` on the schema (same grants `reverse_etl/grant_app_sp.py`
applies to the app SP), and `USE CATALOG`/`USE SCHEMA`/`MODIFY` on
`<catalog>.gold`.

### Trigger

The app's Reports page triggers this job via the Jobs API (`POST
/api/jobs/run-forward-etl`) and polls `GET /api/jobs/runs/{run_id}`.
```

- [ ] **Step 3: Format & lint**

Run: `cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone && uvx ruff format capstone-app/lakebase/ && uvx ruff check --fix capstone-app/lakebase/`
Expected: format clean, `All checks passed!` (the `# Databricks notebook source` and `spark`/`dbutils` globals are fine — ruff won't flag undefined `spark` since it's a notebook; if it does, the file is still a `.py`, so add `# noqa: F821` scoped to the `spark` lines with reason `# noqa: F821 — spark provided by Databricks notebook runtime`).

- [ ] **Step 4: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/lakebase/forward_etl/
git commit -m "feat(t7): forward-ETL drain notebook (Pattern A) + README"
```

---

## Task 2: Backend — config field + run models

Add the job-id setting and the three Pydantic response models. Small, mechanical, gated by a config test.

**Files:**
- Modify: `capstone-app/app/backend/config.py:60-64`
- Modify: `capstone-app/app/backend/models.py` (append after `Page`)
- Test: `capstone-app/app/tests/test_t7_jobs.py` (created here, extended in Task 3)

**Interfaces:**
- Produces: `Settings.forward_etl_job_id: str | None`. Models `RunTrigger {run_id: int}`, `RunStatus {run_id: int, state: str, result_state: str | None, start_time: int | None, duration_ms: int | None, run_page_url: str | None}`, `RunSummary {run_id: int, state: str, result_state: str | None, start_time: int | None, duration_ms: int | None}`.

- [ ] **Step 1: Write the failing test**

Create `capstone-app/app/tests/test_t7_jobs.py`:

```python
"""T7 forward-ETL job endpoint tests via FastAPI TestClient.

The Jobs SDK calls are stubbed by overriding get_sp_client, so these run
without Databricks auth (no `live` marker needed).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.deps import get_sp_client
from backend.main import app


def test_run_models_importable():
    from backend.models import RunStatus, RunSummary, RunTrigger

    t = RunTrigger(run_id=42)
    assert t.run_id == 42
    s = RunStatus(run_id=42, state="RUNNING", result_state=None, start_time=None,
                  duration_ms=None, run_page_url=None)
    assert s.state == "RUNNING"
    assert RunSummary(run_id=1, state="TERMINATED", result_state="SUCCESS",
                      start_time=1, duration_ms=2).result_state == "SUCCESS"


def test_settings_has_forward_etl_job_id():
    assert "forward_etl_job_id" in Settings.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest tests/test_t7_jobs.py -q`
Expected: FAIL — `ImportError: cannot import name 'RunTrigger'` and the settings assertion fails.

- [ ] **Step 3: Add the config field**

In `capstone-app/app/backend/config.py`, after the `dashboard_id` / `genie_space_id` block (around line 64), add:

```python
    # Forward-ETL job id (bundle-injected via the app `job` resource, T7/T8).
    forward_etl_job_id: str | None = None
```

- [ ] **Step 4: Add the response models**

In `capstone-app/app/backend/models.py`, append at the end of the file:

```python
# --- forward-ETL job runs (T7) ----------------------------------------------


class RunTrigger(BaseModel):
    run_id: int


class RunSummary(BaseModel):
    run_id: int
    state: str
    result_state: str | None = None
    start_time: int | None = None
    duration_ms: int | None = None


class RunStatus(RunSummary):
    run_page_url: str | None = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest tests/test_t7_jobs.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Format, lint, commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
uvx ruff format app/ && uvx ruff check --fix app/
git add capstone-app/app/backend/config.py capstone-app/app/backend/models.py capstone-app/app/tests/test_t7_jobs.py
git commit -m "feat(t7): forward_etl_job_id setting + run response models"
```

---

## Task 3: Backend — `jobs.py` router

Three thin Jobs-API endpoints (SP), registered in `main.py`. Verified by stubbed tests + a route-registration test.

**Files:**
- Create: `capstone-app/app/backend/routers/jobs.py`
- Modify: `capstone-app/app/backend/main.py:21,69-71`
- Test: `capstone-app/app/tests/test_t7_jobs.py` (extend)

**Interfaces:**
- Consumes: `Sp` dependency (`WorkspaceClient` as SP), `SettingsDep`, models `RunTrigger`/`RunStatus`/`RunSummary` from Task 2.
- Produces: routes `POST /api/jobs/run-forward-etl`, `GET /api/jobs/runs/{run_id}`, `GET /api/jobs/runs`.

- [ ] **Step 1: Write the failing tests**

Append to `capstone-app/app/tests/test_t7_jobs.py`:

```python
@pytest.fixture
def stub_sp():
    """A WorkspaceClient stub whose .jobs records calls and returns canned runs."""
    calls = {}

    def run_now(job_id):
        calls["run_now"] = job_id
        return SimpleNamespace(run_id=777)

    def get_run(run_id):
        calls["get_run"] = run_id
        return SimpleNamespace(
            run_id=run_id,
            state=SimpleNamespace(
                life_cycle_state=SimpleNamespace(value="RUNNING"),
                result_state=None,
            ),
            start_time=1000,
            run_duration=None,
            run_page_url="https://example/run",
        )

    def list_runs(job_id, limit):
        calls["list_runs"] = (job_id, limit)
        return [
            SimpleNamespace(
                run_id=1,
                state=SimpleNamespace(
                    life_cycle_state=SimpleNamespace(value="TERMINATED"),
                    result_state=SimpleNamespace(value="SUCCESS"),
                ),
                start_time=500,
                run_duration=1234,
            )
        ]

    sp = SimpleNamespace(jobs=SimpleNamespace(
        run_now=run_now, get_run=get_run, list_runs=list_runs))
    sp._calls = calls
    return sp


@pytest.fixture
def client_with_job(stub_sp):
    from backend.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "forward_etl_job_id", "12345")
    app.dependency_overrides[get_sp_client] = lambda: stub_sp
    with TestClient(app) as c:
        yield c, stub_sp
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_jobs_routes_registered():
    paths = set(app.openapi()["paths"].keys())
    assert "/api/jobs/run-forward-etl" in paths
    assert "/api/jobs/runs/{run_id}" in paths
    assert "/api/jobs/runs" in paths


def test_trigger_calls_run_now_with_job_id(client_with_job):
    c, sp = client_with_job
    r = c.post("/api/jobs/run-forward-etl")
    assert r.status_code == 200, r.text
    assert r.json() == {"run_id": 777}
    assert sp._calls["run_now"] == "12345"


def test_get_run_maps_state(client_with_job):
    c, _ = client_with_job
    r = c.get("/api/jobs/runs/777")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == 777
    assert body["state"] == "RUNNING"
    assert body["run_page_url"] == "https://example/run"


def test_list_runs_maps_summary(client_with_job):
    c, sp = client_with_job
    r = c.get("/api/jobs/runs")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows[0]["result_state"] == "SUCCESS"
    assert rows[0]["duration_ms"] == 1234
    assert sp._calls["list_runs"] == ("12345", 10)


def test_endpoints_503_without_job_configured():
    from backend.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "forward_etl_job_id", None)
    app.dependency_overrides[get_sp_client] = lambda: SimpleNamespace(jobs=None)
    with TestClient(app) as c:
        assert c.post("/api/jobs/run-forward-etl").status_code == 503
        assert c.get("/api/jobs/runs").status_code == 503
    app.dependency_overrides.clear()
    get_settings.cache_clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest tests/test_t7_jobs.py -q`
Expected: FAIL — routes not registered (404s), `/api/jobs/*` not in openapi paths.

- [ ] **Step 3: Write the router**

Create `capstone-app/app/backend/routers/jobs.py`:

```python
"""Forward-ETL job endpoints (T7).

Three thin wrappers over the Jobs API, run as the app SP (background work, not
user-attributed). The app never runs the drain itself — it triggers the
serverless notebook job declared in the bundle (resources/jobs.yml) and polls
its run status. The job id is bundle-injected via FORWARD_ETL_JOB_ID.
"""

from __future__ import annotations

import asyncio

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..deps import Sp
from ..models import RunStatus, RunSummary, RunTrigger

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_id() -> str:
    job_id = get_settings().forward_etl_job_id
    if not job_id:
        raise HTTPException(status_code=503, detail="forward-ETL job not configured")
    return job_id


def _state(run) -> tuple[str, str | None]:
    """(life_cycle_state, result_state) as plain strings."""
    st = run.state
    life = getattr(st.life_cycle_state, "value", None) or str(st.life_cycle_state)
    result = getattr(st.result_state, "value", None) if st and st.result_state else None
    return life, result


def _trigger(w: WorkspaceClient, job_id: str) -> RunTrigger:
    run = w.jobs.run_now(job_id)
    return RunTrigger(run_id=run.run_id)


def _get_run(w: WorkspaceClient, run_id: int) -> RunStatus:
    run = w.jobs.get_run(run_id)
    life, result = _state(run)
    return RunStatus(
        run_id=run.run_id,
        state=life,
        result_state=result,
        start_time=run.start_time,
        duration_ms=getattr(run, "run_duration", None),
        run_page_url=getattr(run, "run_page_url", None),
    )


def _list_runs(w: WorkspaceClient, job_id: str) -> list[RunSummary]:
    runs = w.jobs.list_runs(job_id=job_id, limit=10)
    out: list[RunSummary] = []
    for run in runs:
        life, result = _state(run)
        out.append(
            RunSummary(
                run_id=run.run_id,
                state=life,
                result_state=result,
                start_time=run.start_time,
                duration_ms=getattr(run, "run_duration", None),
            )
        )
    return out


@router.post("/run-forward-etl", response_model=RunTrigger)
async def run_forward_etl(sp: Sp) -> RunTrigger:
    return await asyncio.to_thread(_trigger, sp, _job_id())


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: int, sp: Sp) -> RunStatus:
    _job_id()  # 503 if not configured
    return await asyncio.to_thread(_get_run, sp, run_id)


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(sp: Sp) -> list[RunSummary]:
    return await asyncio.to_thread(_list_runs, sp, _job_id())
```

Note: `list_runs(job_id=...)` returns an iterable of `BaseRun`; the SDK's `limit` param caps page size. If the installed SDK signature differs, run `python -c "from databricks.sdk import WorkspaceClient; help(WorkspaceClient.jobs.list_runs)"` and adjust — but keep the return shape.

- [ ] **Step 4: Register the router**

In `capstone-app/app/backend/main.py`, line 21, change:

```python
from .routers import customers, dashboard, genie
```
to:
```python
from .routers import customers, dashboard, genie, jobs
```

After line 71 (`app.include_router(genie.router)`), add:

```python
app.include_router(jobs.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest tests/test_t7_jobs.py -q`
Expected: PASS (all tests).

- [ ] **Step 6: Full suite + format + lint**

Run:
```bash
cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk --with python-dotenv --with pytest pytest -q
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone && uvx ruff format app/ && uvx ruff check --fix app/
```
Expected: whole suite green (live tests skip), ruff clean.

- [ ] **Step 7: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/app/backend/routers/jobs.py capstone-app/app/backend/main.py capstone-app/app/tests/test_t7_jobs.py
git commit -m "feat(t7): /api/jobs endpoints to trigger + poll forward-ETL"
```

---

## Task 4: Frontend — data layer (types, api, queries)

Add run types, the `jobs` api namespace, and TanStack hooks. Verified by tsc.

**Files:**
- Modify: `capstone-app/app/frontend/src/lib/types.ts` (append)
- Modify: `capstone-app/app/frontend/src/lib/api.ts` (add `jobs` to `api`)
- Modify: `capstone-app/app/frontend/src/lib/queries.ts` (append)

**Interfaces:**
- Consumes: backend routes from Task 3.
- Produces: `api.jobs.{runForwardEtl, getRun, listRuns}`; hooks `useForwardEtlRuns()`, `useRunForwardEtl()`, `useForwardEtlRun(runId, enabled)`.

- [ ] **Step 1: Add types**

Append to `capstone-app/app/frontend/src/lib/types.ts`:

```typescript
export interface RunTrigger {
  run_id: number;
}

export interface RunSummary {
  run_id: number;
  state: string;
  result_state: string | null;
  start_time: number | null;
  duration_ms: number | null;
}

export interface RunStatus extends RunSummary {
  run_page_url: string | null;
}
```

- [ ] **Step 2: Add the api namespace**

In `capstone-app/app/frontend/src/lib/api.ts`, add the new types to the import block at the top:

```typescript
  RunStatus,
  RunSummary,
  RunTrigger,
```

Then, inside the `export const api = { ... }` object, after the `genie: { ... }` namespace (before the closing `}`), add:

```typescript
  jobs: {
    runForwardEtl: () => request<RunTrigger>("/jobs/run-forward-etl", { method: "POST" }),
    getRun: (runId: number) => request<RunStatus>(`/jobs/runs/${runId}`),
    listRuns: () => request<RunSummary[]>("/jobs/runs"),
  },
```

- [ ] **Step 3: Add the query hooks**

Append to `capstone-app/app/frontend/src/lib/queries.ts`:

```typescript
const TERMINAL_RUN = new Set(["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]);

export function useForwardEtlRuns() {
  return useQuery({
    queryKey: ["jobs", "runs"] as const,
    queryFn: () => api.jobs.listRuns(),
    staleTime: 5_000,
    retry: 1,
  });
}

export function useRunForwardEtl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.jobs.runForwardEtl(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", "runs"] }),
  });
}

// Polls one run while its state is non-terminal; refreshes the runs list when
// it settles. `enabled` gates polling to an in-flight run id.
export function useForwardEtlRun(runId: number | null, enabled: boolean) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["jobs", "run", runId] as const,
    queryFn: () => api.jobs.getRun(runId as number),
    enabled: enabled && runId != null,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      if (state && TERMINAL_RUN.has(state)) {
        qc.invalidateQueries({ queryKey: ["jobs", "runs"] });
        return false;
      }
      return 2_000;
    },
  });
}
```

- [ ] **Step 4: Typecheck**

Run: `cd app/frontend && bunx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/app/frontend/src/lib/types.ts capstone-app/app/frontend/src/lib/api.ts capstone-app/app/frontend/src/lib/queries.ts
git commit -m "feat(t7): frontend data layer for forward-ETL runs"
```

---

## Task 5: Frontend — `Reports.tsx` + route

The Reports page: run button + live status + recent-runs table, cockpit-styled. Verified by tsc + build.

**Files:**
- Create: `capstone-app/app/frontend/src/pages/Reports.tsx`
- Modify: `capstone-app/app/frontend/src/main.tsx:13,49-54`

**Interfaces:**
- Consumes: `useForwardEtlRuns`, `useRunForwardEtl`, `useForwardEtlRun` from Task 4; `Panel`, `PanelHeader`, `Button` from `components/ui`; `EmptyState`, `ErrorState`, `TableSkeleton` from `components/states`; `useToast` from `components/toast`.

- [ ] **Step 1: Write the Reports page**

Create `capstone-app/app/frontend/src/pages/Reports.tsx`:

```tsx
import { ExternalLink, Play } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { useToast } from "@/components/toast";
import { Button, Panel, PanelHeader } from "@/components/ui";
import { useForwardEtlRun, useForwardEtlRuns, useRunForwardEtl } from "@/lib/queries";
import type { RunSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const TERMINAL = new Set(["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]);

function tone(state: string, result: string | null): "green" | "amber" | "alert" {
  if (!TERMINAL.has(state)) return "amber"; // running / pending
  if (result === "SUCCESS") return "green";
  return "alert";
}

const TONE_CLS: Record<string, string> = {
  green: "border-green/50 text-green bg-green/10",
  amber: "border-amber/60 text-amber bg-amber/10",
  alert: "border-alert/60 text-alert bg-alert/10",
};

function StatePill({ state, result }: { state: string; result: string | null }) {
  const t = tone(state, result);
  const label = TERMINAL.has(state) ? (result ?? state) : state;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider",
        TONE_CLS[t],
      )}
    >
      {label}
    </span>
  );
}

function fmtTime(ms: number | null): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleString();
}

function fmtDuration(ms: number | null): string {
  if (!ms) return "—";
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function Reports() {
  const runs = useForwardEtlRuns();
  const trigger = useRunForwardEtl();
  const toast = useToast();
  const [activeRun, setActiveRun] = useState<number | null>(null);

  const inFlight = activeRun != null;
  const active = useForwardEtlRun(activeRun, inFlight);
  const activeSettled = active.data && TERMINAL.has(active.data.state);
  const busy = trigger.isPending || (inFlight && !activeSettled);

  async function onRun() {
    try {
      const { run_id } = await trigger.mutateAsync();
      setActiveRun(run_id);
      toast("ok", `Forward-ETL run ${run_id} started`);
    } catch (e) {
      toast("err", e instanceof Error ? e.message : "Failed to start run");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl uppercase tracking-[0.12em] text-lum">
            Forward ETL
          </h1>
          <p className="font-mono text-xs text-muted">
            Promote staging notes &amp; overrides → Delta gold
          </p>
        </div>
        <Button onClick={onRun} disabled={busy}>
          <Play className="h-4 w-4" strokeWidth={2} />
          {busy ? "Running…" : "Run forward-ETL"}
        </Button>
      </div>

      {active.data && (
        <Panel className="mb-4">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">
                Run {active.data.run_id}
              </span>
              <StatePill state={active.data.state} result={active.data.result_state} />
            </div>
            {active.data.run_page_url && (
              <a
                href={active.data.run_page_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-mono text-[11px] text-muted hover:text-lum"
              >
                <ExternalLink className="h-3.5 w-3.5" /> workspace
              </a>
            )}
          </div>
        </Panel>
      )}

      <Panel>
        <PanelHeader>
          <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">
            Recent runs
          </span>
        </PanelHeader>
        {runs.isLoading ? (
          <TableSkeleton rows={5} />
        ) : runs.isError ? (
          <ErrorState message="Could not load run history." onRetry={() => runs.refetch()} />
        ) : !runs.data || runs.data.length === 0 ? (
          <EmptyState title="No runs yet" hint="Trigger a forward-ETL run to see history." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr className="text-left text-muted">
                  <th className="px-4 py-2 font-normal">Run</th>
                  <th className="px-4 py-2 font-normal">State</th>
                  <th className="px-4 py-2 font-normal">Started</th>
                  <th className="px-4 py-2 font-normal">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r: RunSummary) => (
                  <tr key={r.run_id} className="border-t border-bezel/60 text-lum/90">
                    <td className="px-4 py-2">{r.run_id}</td>
                    <td className="px-4 py-2">
                      <StatePill state={r.state} result={r.result_state} />
                    </td>
                    <td className="px-4 py-2">{fmtTime(r.start_time)}</td>
                    <td className="px-4 py-2">{fmtDuration(r.duration_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
```

- [ ] **Step 2: Wire the route**

In `capstone-app/app/frontend/src/main.tsx`, after line 13 (`const Dashboard = lazy(...)`), add:

```tsx
const Reports = lazy(() => import("./pages/Reports"));
```

Replace the `reports` route element:

```tsx
      {
        path: "reports",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <ComingSoon title="Reports" note="Forward-ETL controls land in T7." />
          </Suspense>
        ),
      },
```
with:
```tsx
      {
        path: "reports",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <Reports />
          </Suspense>
        ),
      },
```

If `ComingSoon` is now unused (grep `main.tsx` for `ComingSoon` — only the import and the removed usage should reference it), remove its import line `const ComingSoon = lazy(() => import("./pages/ComingSoon"));`. Leave `pages/ComingSoon.tsx` on disk (pre-existing; not our mess to delete).

- [ ] **Step 3: Typecheck + build**

Run:
```bash
cd app/frontend && bunx tsc --noEmit && bun run build
```
Expected: tsc clean; build succeeds, emits to `app/backend/static/`.

- [ ] **Step 4: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/app/frontend/src/pages/Reports.tsx capstone-app/app/frontend/src/main.tsx capstone-app/app/backend/static/
git commit -m "feat(t7): Reports page — run forward-ETL, live status, run history"
```

---

## Task 6: DABs wiring — job resource + app binding + env

Declare the job in the bundle, bind it to the app, inject its id. Verified by `bundle validate`.

**Files:**
- Create: `resources/jobs.yml` (repo root)
- Modify: `resources/app.yml` (repo root)
- Modify: `capstone-app/app/app.yaml`

**Interfaces:**
- Consumes: notebook from Task 1; `FORWARD_ETL_JOB_ID` read by `Settings.forward_etl_job_id` (Task 2).

- [ ] **Step 1: Create the job resource**

Create `resources/jobs.yml`:

```yaml
resources:
  jobs:
    forward_etl:
      name: "customer360 forward-ETL (${bundle.target})"
      tasks:
        - task_key: drain_staging
          notebook_task:
            notebook_path: ../capstone-app/lakebase/forward_etl/pattern_a_psycopg2/drain_staging.py
          environment_key: default
      environments:
        - environment_key: default
          spec:
            client: "3"
            dependencies:
              - "psycopg[binary]"
              - "databricks-sdk"
```

Note: `notebook_path` is relative to `resources/` (per the DABs path rule). Serverless jobs use `environment_key` + a matching `environments` entry with `client: "3"`.

- [ ] **Step 2: Bind the job to the app**

In `resources/app.yml`, inside the app's `resources:` list (after the `genie-space` entry, keeping list style consistent), add:

```yaml
        - name: forward-etl-job
          job:
            id: ${resources.jobs.forward_etl.id}
            permission: "CAN_MANAGE_RUN"
```

- [ ] **Step 3: Inject the env var**

In `capstone-app/app/app.yaml`, add to the `env:` list:

```yaml
  - { name: "FORWARD_ETL_JOB_ID", valueFrom: "forward-etl-job" }
```

`valueFrom` references the app resource `name` (`forward-etl-job`) — the runtime resolves it to the bound job's id.

- [ ] **Step 4: Validate the bundle**

Run: `cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone && databricks bundle validate --target dev --profile fevm-test-jg`
Expected: validation passes; output shows the `forward_etl` job and the app's `forward-etl-job` resource. If validate complains that `valueFrom` must reference a declared resource, confirm the `name` matches exactly (`forward-etl-job`).

- [ ] **Step 5: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add resources/jobs.yml resources/app.yml capstone-app/app/app.yaml
git commit -m "feat(t7): DABs forward-ETL job resource + app binding + env"
```

---

## Task 7: Deploy, wire grants, live verification

Deploy the bundle, ensure the job SP can reach Lakebase + gold, run the drain end-to-end from the Reports page, verify idempotency. Manual/live — no unit tests.

**Files:** none (operational). May extend `capstone-app/lakebase/reverse_etl/grant_app_sp.py` only if the prod job SP differs from the app SP and lacks grants.

- [ ] **Step 1: Deploy**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git push
databricks bundle deploy --target dev --profile fevm-test-jg
databricks bundle run customer360 --target dev --profile fevm-test-jg
```
Expected: app starts; the `forward_etl` job now exists in the workspace. (Reminder: the git-source app pulls from the `t5` branch — push before `bundle run`.)

- [ ] **Step 2: Confirm the job id reached the app**

Check the app can see `FORWARD_ETL_JOB_ID`: hit the Reports page in the browser, or `databricks apps logs customer360-dev --profile fevm-test-jg` after clicking "Run forward-ETL". A `503 forward-ETL job not configured` means the binding/env didn't resolve — re-check Task 6.

- [ ] **Step 3: Grants for the job run-as identity**

In dev the job runs as the deploying user (project owner) — already has Lakebase + gold access, so likely nothing to do. If the run fails with a Postgres permission error on the staging tables, or a UC `MODIFY`/`USE` error on `gold`, grant the run-as identity: reuse `reverse_etl/grant_app_sp.py` against that SP for the staging `SELECT`/`UPDATE`, and grant `USE CATALOG test_jg_catalog` / `USE SCHEMA gold` / `MODIFY` on the two gold tables via SQL.

- [ ] **Step 4: End-to-end run**

Add a note via the app UI (creates an unprocessed `customer_notes_staging` row). On the Reports page, click **Run forward-ETL**. Watch the live status pill go RUNNING → SUCCESS. Verify:

```bash
databricks experimental aitools tools query \
  "SELECT COUNT(*) FROM test_jg_catalog.gold.customer_notes" --profile fevm-test-jg
```
Expected: rowcount equals the number of `processed=true` notes in staging.

- [ ] **Step 5: Idempotency**

Click **Run forward-ETL** again with no new staging rows. Check the job run output: `notes drained: 0`, `overrides drained: 0`. Re-query gold — rowcount unchanged.

- [ ] **Step 6: Commit any grant-script changes (only if made)**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/lakebase/reverse_etl/grant_app_sp.py
git commit -m "chore(t7): grant forward-ETL job SP access to staging + gold"
```

---

## Self-Review Notes

- **Spec coverage:** notebook (Task 1) ✓; `POST /run-forward-etl` + `GET /runs/{id}` + `GET /runs` (Task 3) ✓; `Reports.tsx` button+status+history (Task 5) ✓; DABs job + binding + env (Task 6) ✓; run-as grants prereq (Task 7 step 3) ✓; all three "Done when" checks (Task 7 steps 4–5) ✓; MERGE-first crash safety (Task 1 + README) ✓; both gold targets, audit_log excluded ✓.
- **Type consistency:** `RunTrigger`/`RunStatus`/`RunSummary` fields identical across models.py (Task 2), test stubs (Task 3), types.ts (Task 4), Reports.tsx (Task 5). `duration_ms` maps from SDK `run_duration`. `forward_etl_job_id` consistent config↔env (`FORWARD_ETL_JOB_ID`). Terminal-state set (`TERMINATED`/`SKIPPED`/`INTERNAL_ERROR`) identical in queries.ts and Reports.tsx.
- **Verify-before-code note for implementer:** the Jobs SDK `run_now`/`get_run`/`list_runs` field names (`run_duration`, `run_page_url`, `state.result_state`) are the expected shape; if the installed `databricks-sdk` differs, adjust the mapper in `jobs.py` `_get_run`/`_list_runs` and keep the response model shape — the tests stub these, so update stubs to match reality if you change the mapping.
