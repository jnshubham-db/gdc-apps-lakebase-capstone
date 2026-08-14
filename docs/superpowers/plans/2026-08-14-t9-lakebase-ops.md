# T9 — Lakebase ops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demonstrate Lakebase Autoscaling branching + PITR (T9a) and query-index insights (T9b) with reproducible scripts and a screenshot writeup, never touching `production` destructively.

**Architecture:** Two standalone driver scripts under `capstone-app/lakebase/ops/`, sharing a `_common.py` that wraps the `databricks postgres` CLI (branch lifecycle, endpoint host/token) and opens psycopg connections to arbitrary branch endpoints. All destructive/seeding work runs on short-TTL child branches of `projects/capstone-pg`. Scripts print the numbers a human pastes (with UI screenshots) into `docs/t9-lakebase-ops-writeup.md`.

**Tech Stack:** Python 3.11, psycopg 3, `databricks` CLI (`postgres` group, Beta), `uv` for ad-hoc deps, pytest for the one pure helper. Ruff for format/lint.

## Global Constraints

- Python formatted + lint-clean with ruff before commit: `uvx ruff format app/ lakebase/` and `uvx ruff check --fix app/ lakebase/` (config `app/pyproject.toml`, line-length 100, py311). Both must pass.
- Conventional commits, scoped `t9`. Branch `t9`, stacked on `t5`.
- Lakebase project `projects/capstone-pg` (Autoscaling, PG 16). Profile from `app/.env` `DATABRICKS_PROFILE` (`fevm-test-jg`). DB `capstone_db`. 7-day PITR window.
- **Never** run destructive SQL or seed rows against `branches/production`. All such work happens on child branches, deleted at the end unless `--keep`.
- Scripts read config from `app/.env` (same pattern as `lakebase/reverse_etl/_common.py`); run as the project owner from a laptop.
- Run scripts with: `cd capstone-app/lakebase/ops && uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv python <script>.py`.

---

### Task 1: `lakebase/ops/_common.py` — CLI + DB helpers, percentile util

**Files:**
- Create: `capstone-app/lakebase/ops/_common.py`
- Test: `capstone-app/lakebase/ops/test_common.py`

**Interfaces:**
- Produces:
  - `load_cfg() -> dict[str, str]` — reads `app/.env`, requires `DATABRICKS_PROFILE`, `PGDATABASE`; returns all keys.
  - `cli_json(*args: str, profile: str)` -> parsed JSON (dict or list) from `databricks <args> -o json`.
  - `current_user(profile: str) -> str`
  - `create_branch(profile, project, branch_id, *, source_branch=None, source_branch_time=None, ttl="14400s", replace=True) -> str` — returns branch resource path `projects/{p}/branches/{branch_id}`.
  - `delete_branch(profile, branch_path) -> None`
  - `readwrite_endpoint(profile, branch_path) -> str` — returns the branch's first endpoint resource path.
  - `endpoint_host(profile, endpoint_path) -> str`
  - `endpoint_token(profile, endpoint_path) -> str`
  - `connect(host, user, dbname, token)` -> `psycopg.Connection`
  - `percentiles(samples_ms: list[float], pcts=(50, 95, 99)) -> dict[int, float]`

- [ ] **Step 1: Write the failing test for `percentiles`**

```python
# capstone-app/lakebase/ops/test_common.py
from _common import percentiles


def test_percentiles_basic():
    samples = [float(i) for i in range(1, 101)]  # 1..100 ms
    p = percentiles(samples, pcts=(50, 95, 99))
    assert p[50] == 50.0
    assert p[95] == 95.0
    assert p[99] == 99.0


def test_percentiles_single_sample():
    assert percentiles([7.0], pcts=(50, 95))[95] == 7.0
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd capstone-app/lakebase/ops && uv run --with pytest python -m pytest test_common.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'percentiles'`.

- [ ] **Step 3: Write `_common.py`**

```python
"""Shared helpers for the T9 Lakebase-ops scripts.

Wraps the ``databricks postgres`` CLI (branch lifecycle, endpoint host/token)
and opens psycopg connections to an arbitrary branch endpoint. Run by a human
operator (project owner) from a laptop — never by the deployed app.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import psycopg
from dotenv import dotenv_values

# repo layout: capstone-app/lakebase/ops/_common.py -> capstone-app/app/.env
_ENV_PATH = Path(__file__).resolve().parents[2] / "app" / ".env"


def load_cfg() -> dict[str, str]:
    if not _ENV_PATH.exists():
        raise FileNotFoundError(f"Expected capstone config at {_ENV_PATH}")
    cfg = {k: v for k, v in dotenv_values(_ENV_PATH).items() if v is not None}
    missing = [k for k in ("DATABRICKS_PROFILE", "PGDATABASE") if not cfg.get(k)]
    if missing:
        raise KeyError(f"Missing keys in {_ENV_PATH}: {', '.join(missing)}")
    return cfg


def cli_json(*args: str, profile: str):
    """Run ``databricks <args> -o json --profile <profile>`` and parse stdout."""
    cmd = ["databricks", *args, "-o", "json", "--profile", profile]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def current_user(profile: str) -> str:
    return cli_json("current-user", "me", profile=profile)["userName"]


def create_branch(
    profile: str,
    project: str,
    branch_id: str,
    *,
    source_branch: str | None = None,
    source_branch_time: str | None = None,
    ttl: str = "14400s",
    replace: bool = True,
) -> str:
    """Create a branch; return its resource path. PITR via source_branch_time (RFC3339)."""
    spec: dict[str, object] = {"ttl": ttl}
    if source_branch:
        spec["source_branch"] = source_branch
    if source_branch_time:
        spec["source_branch_time"] = source_branch_time
    args = ["postgres", "create-branch", f"projects/{project}", branch_id, "--json", json.dumps({"spec": spec})]
    if replace:
        args.append("--replace-existing")
    cli_json(*args, profile=profile)
    return f"projects/{project}/branches/{branch_id}"


def delete_branch(profile: str, branch_path: str) -> None:
    subprocess.run(
        ["databricks", "postgres", "delete-branch", branch_path, "--profile", profile],
        capture_output=True,
        text=True,
        check=True,
    )


def readwrite_endpoint(profile: str, branch_path: str) -> str:
    data = cli_json("postgres", "list-endpoints", branch_path, profile=profile)
    endpoints = data if isinstance(data, list) else data.get("endpoints", [])
    if not endpoints:
        raise RuntimeError(f"No endpoints on {branch_path}")
    return endpoints[0]["name"]


def endpoint_host(profile: str, endpoint_path: str) -> str:
    return cli_json("postgres", "get-endpoint", endpoint_path, profile=profile)["status"]["hosts"]["host"]


def endpoint_token(profile: str, endpoint_path: str) -> str:
    return cli_json("postgres", "generate-database-credential", endpoint_path, profile=profile)["token"]


def connect(host: str, user: str, dbname: str, token: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=int(os.getenv("PGPORT", "5432")),
        dbname=dbname,
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )


def percentiles(samples_ms: list[float], pcts=(50, 95, 99)) -> dict[int, float]:
    """Nearest-rank percentiles over the sample list (ms)."""
    if not samples_ms:
        raise ValueError("no samples")
    ordered = sorted(samples_ms)
    out: dict[int, float] = {}
    for p in pcts:
        rank = max(1, math.ceil(p / 100 * len(ordered)))
        out[p] = ordered[rank - 1]
    return out
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd capstone-app/lakebase/ops && uv run --with pytest python -m pytest test_common.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Ruff + commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
uvx ruff format capstone-app/lakebase/ && uvx ruff check --fix capstone-app/lakebase/
git add capstone-app/lakebase/ops/_common.py capstone-app/lakebase/ops/test_common.py
git commit -m "feat(t9): lakebase ops helpers — branch CLI, endpoint auth, percentiles"
```

---

### Task 2: `t9a_branch_pitr.py` — branch + PITR driver

**Files:**
- Create: `capstone-app/lakebase/ops/t9a_branch_pitr.py`

**Interfaces:**
- Consumes: `_common.load_cfg, create_branch, delete_branch, readwrite_endpoint, endpoint_host, endpoint_token, current_user, connect`.
- Produces: CLI `python t9a_branch_pitr.py [--keep]`. Prints branch paths, pre-delete count `N`, post-delete count `0`, `production` count (unchanged), and post-restore count (== `N`).

- [ ] **Step 1: Write the driver**

```python
"""T9a — branching + PITR demo on a child of projects/capstone-pg.

Flow (production is NEVER modified):
  1. create child branch `capstone-pitr-demo` from production   [screenshot: branch creation]
  2. record N = count(customer_notes_staging) on the child, then T0
  3. DELETE FROM customer_notes_staging on the child  -> 0 rows
  4. assert production count unchanged (isolation proof)
  5. PITR: create `capstone-pitr-restored` from the child AT T0 -> count == N  [screenshot: row count]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import _common as c

PROJECT = "capstone-pg"
DEMO = "capstone-pitr-demo"
RESTORED = "capstone-pitr-restored"
STAGING = "customer_notes_staging"


def _count(profile: str, branch_path: str, cfg: dict, user: str) -> int:
    ep = c.readwrite_endpoint(profile, branch_path)
    host = c.endpoint_host(profile, ep)
    token = c.endpoint_token(profile, ep)
    with c.connect(host, user, cfg["PGDATABASE"], token) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {STAGING}")
        return cur.fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="do not delete demo branches at the end")
    args = ap.parse_args()

    cfg = c.load_cfg()
    profile = cfg["DATABRICKS_PROFILE"]
    user = c.current_user(profile)
    prod = f"projects/{PROJECT}/branches/production"

    prod_before = _count(profile, prod, cfg, user)
    print(f"production {STAGING} rows (baseline): {prod_before}")

    print(f"\n[1] creating child branch {DEMO} from production ...")
    demo = c.create_branch(profile, PROJECT, DEMO, source_branch=prod)
    print(f"    created {demo}   <-- screenshot 1: branch creation (Lakebase UI)")

    n = _count(profile, demo, cfg, user)
    print(f"[2] {DEMO} {STAGING} rows: {n}")
    time.sleep(5)  # ensure T0 is safely after branch creation / WAL settle
    t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"    T0 (before delete) = {t0}")
    time.sleep(2)

    print(f"[3] DELETE FROM {STAGING} on {DEMO} ...")
    ep = c.readwrite_endpoint(profile, demo)
    host, token = c.endpoint_host(profile, ep), c.endpoint_token(profile, ep)
    with c.connect(host, user, cfg["PGDATABASE"], token) as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {STAGING}")
        conn.commit()
        cur.execute(f"SELECT count(*) FROM {STAGING}")
        print(f"    {DEMO} {STAGING} rows after delete: {cur.fetchone()[0]}")

    prod_after = _count(profile, prod, cfg, user)
    print(f"[4] production {STAGING} rows (must equal baseline): {prod_after}")
    assert prod_after == prod_before, "ISOLATION VIOLATED: production changed!"
    print("    isolation OK — production untouched")

    print(f"\n[5] PITR: creating {RESTORED} from {DEMO} at {t0} ...")
    restored = c.create_branch(profile, PROJECT, RESTORED, source_branch=demo, source_branch_time=t0)
    restored_n = _count(profile, restored, cfg, user)
    print(f"    {RESTORED} {STAGING} rows: {restored_n}   <-- screenshot 2: post-restore row count")
    assert restored_n == n, f"PITR restored {restored_n}, expected {n}"
    print(f"    PITR OK — recovered {restored_n} rows deleted on {DEMO}")

    if not args.keep:
        print("\ncleanup: deleting demo branches ...")
        for b in (restored, demo):
            c.delete_branch(profile, b)
            print(f"    deleted {b}")
    else:
        print("\n--keep set: leaving demo branches in place (delete manually later)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ruff format/lint**

Run: `cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone && uvx ruff format capstone-app/lakebase/ && uvx ruff check --fix capstone-app/lakebase/`
Expected: format clean, `All checks passed!`.

- [ ] **Step 3: Run live, keeping branches for screenshots**

Run: `cd capstone-app/lakebase/ops && uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv python t9a_branch_pitr.py --keep`
Expected: prints baseline == post-isolation prod count; `restored_n == n`; no assertion errors.

If PITR rejects `source_branch_time` as too recent, increase the `time.sleep(5)` before T0 (or branch from `production` at T0 as a documented fallback) and re-run.

- [ ] **Step 4: Capture screenshots**

In the Lakebase UI for `capstone-pg`: screenshot the **Branches** list showing `capstone-pitr-demo` (branch creation), and a query/console showing `capstone-pitr-restored`'s `customer_notes_staging` row count == `N`. Save under `capstone-app/docs/img/` as `t9a-branch-creation.png` and `t9a-post-restore-count.png`.

- [ ] **Step 5: Clean up branches**

Run: `cd capstone-app/lakebase/ops && uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv python -c "import _common as c;cfg=c.load_cfg();p=cfg['DATABRICKS_PROFILE'];[c.delete_branch(p,f'projects/capstone-pg/branches/{b}') for b in ('capstone-pitr-restored','capstone-pitr-demo')]"`
Expected: both branches deleted (verify with `databricks postgres list-branches projects/capstone-pg --profile fevm-test-jg`).

- [ ] **Step 6: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/lakebase/ops/t9a_branch_pitr.py capstone-app/docs/img/t9a-*.png
git commit -m "feat(t9a): branch + PITR driver, isolation + recovery proof"
```

---

### Task 3: `t9b_query_insights.py` — seed, measure, index, re-measure

**Files:**
- Create: `capstone-app/lakebase/ops/t9b_query_insights.py`

**Interfaces:**
- Consumes: `_common.load_cfg, create_branch, delete_branch, readwrite_endpoint, endpoint_host, endpoint_token, current_user, connect, percentiles`.
- Produces: CLI `python t9b_query_insights.py [--rows 200000] [--iters 100] [--keep]`. Prints before/after p50/p95/p99 (ms), the `EXPLAIN` plan node before (Seq Scan) and after (Index Scan), and a best-effort `pg_stat_statements` mean.

- [ ] **Step 1: Write the driver**

```python
"""T9b — query insights: seq scan vs index on customer_audit_log.actor_email.

Runs on a dedicated child branch `capstone-perf-demo` (production untouched):
  1. CREATE EXTENSION pg_stat_statements (best effort)
  2. seed ~200k synthetic rows across ~1000 distinct actor_emails
  3. run `WHERE actor_email = :target` 100x, time each -> p50/p95/p99 (BEFORE)
  4. CREATE INDEX ... (actor_email); ANALYZE
  5. re-run 100x -> p50/p95/p99 (AFTER)
Captures EXPLAIN plans before/after for the writeup.
"""

from __future__ import annotations

import argparse
import time

import _common as c

PROJECT = "capstone-pg"
PERF = "capstone-perf-demo"
TABLE = "customer_audit_log"
TARGET = "perf500@example.com"  # ~rows/1000 matches; selective slice
QUERY = f"SELECT audit_id, customer_id, action, created_at FROM {TABLE} WHERE actor_email = %s"


def _seed(cur, rows: int) -> None:
    cur.execute(
        f"""
        INSERT INTO {TABLE} (customer_id, action, actor_email, payload)
        SELECT 'C' || lpad((g %% 10000)::text, 7, '0'),
               'seed',
               'perf' || (g %% 1000)::text || '@example.com',
               '{{}}'::jsonb
        FROM generate_series(1, %s) AS g
        """,
        (rows,),
    )


def _timed_runs(cur, iters: int) -> list[float]:
    samples = []
    for _ in range(iters):
        t = time.perf_counter()
        cur.execute(QUERY, (TARGET,))
        cur.fetchall()
        samples.append((time.perf_counter() - t) * 1000.0)
    return samples


def _explain(cur) -> str:
    cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + QUERY, (TARGET,))
    return "\n".join(r[0] for r in cur.fetchall())


def _report(label: str, samples: list[float]) -> None:
    p = c.percentiles(samples)
    print(f"  {label}: p50={p[50]:.2f}ms  p95={p[95]:.2f}ms  p99={p[99]:.2f}ms  (n={len(samples)})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    cfg = c.load_cfg()
    profile = cfg["DATABRICKS_PROFILE"]
    user = c.current_user(profile)

    print(f"[setup] creating perf branch {PERF} from production ...")
    perf = c.create_branch(profile, PROJECT, PERF, source_branch=f"projects/{PROJECT}/branches/production")
    ep = c.readwrite_endpoint(profile, perf)
    host, token = c.endpoint_host(profile, ep), c.endpoint_token(profile, ep)

    try:
        with c.connect(host, user, cfg["PGDATABASE"], token) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                    has_pgss = True
                except Exception as e:  # noqa: BLE001 — extension may not be preloaded
                    print(f"  pg_stat_statements unavailable: {e}")
                    has_pgss = False

                print(f"[seed] inserting {args.rows} rows into {TABLE} ...")
                _seed(cur, args.rows)
                cur.execute(f"SELECT count(*) FROM {TABLE} WHERE actor_email = %s", (TARGET,))
                print(f"  target '{TARGET}' matches {cur.fetchone()[0]} rows")
                cur.execute(f"ANALYZE {TABLE}")

                print("\n[before] EXPLAIN (no index):")
                print(_explain(cur))
                if has_pgss:
                    cur.execute("SELECT pg_stat_statements_reset()")
                _report("BEFORE", _timed_runs(cur, args.iters))

                print("\n[index] CREATE INDEX ON customer_audit_log (actor_email); ANALYZE")
                cur.execute(f"CREATE INDEX idx_audit_actor_email ON {TABLE} (actor_email)")
                cur.execute(f"ANALYZE {TABLE}")

                print("\n[after] EXPLAIN (with index):")
                print(_explain(cur))
                if has_pgss:
                    cur.execute("SELECT pg_stat_statements_reset()")
                _report("AFTER", _timed_runs(cur, args.iters))

                if has_pgss:
                    cur.execute(
                        "SELECT calls, mean_exec_time FROM pg_stat_statements "
                        "WHERE query LIKE %s ORDER BY calls DESC LIMIT 1",
                        (f"%{TABLE}%actor_email%",),
                    )
                    row = cur.fetchone()
                    if row:
                        print(f"\n  pg_stat_statements (after): calls={row[0]} mean_exec_time={row[1]:.3f}ms")
    finally:
        if not args.keep:
            print("\ncleanup: deleting perf branch ...")
            c.delete_branch(profile, perf)
            print(f"    deleted {perf}")
        else:
            print("\n--keep set: leaving perf branch in place")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ruff format/lint**

Run: `cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone && uvx ruff format capstone-app/lakebase/ && uvx ruff check --fix capstone-app/lakebase/`
Expected: format clean, `All checks passed!`.

- [ ] **Step 3: Run live, keep branch for screenshots**

Run: `cd capstone-app/lakebase/ops && uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv python t9b_query_insights.py --keep`
Expected: BEFORE EXPLAIN shows `Seq Scan on customer_audit_log`; AFTER shows `Index Scan using idx_audit_actor_email`; AFTER p95 markedly lower than BEFORE p95.

- [ ] **Step 4: Capture screenshots + numbers**

In the Lakebase UI **Query Performance** (or `pg_stat_statements`) for `capstone-perf-demo`, screenshot the `actor_email` query row before vs. after the index (save `capstone-app/docs/img/t9b-before.png`, `t9b-after.png`). Copy the printed BEFORE/AFTER p50/p95/p99 and both EXPLAIN plans into the writeup in Task 4.

- [ ] **Step 5: Clean up branch**

Run: `databricks postgres delete-branch projects/capstone-pg/branches/capstone-perf-demo --profile fevm-test-jg` (verify with `list-branches`).

- [ ] **Step 6: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/lakebase/ops/t9b_query_insights.py capstone-app/docs/img/t9b-*.png
git commit -m "feat(t9b): query-insights driver — seed, seq-scan vs index p95"
```

---

### Task 4: Runbook README + writeup

**Files:**
- Create: `capstone-app/lakebase/ops/README.md`
- Create: `capstone-app/docs/t9-lakebase-ops-writeup.md`

- [ ] **Step 1: Write `lakebase/ops/README.md`**

```markdown
# T9 — Lakebase ops

Reproducible drivers for the two T9 exercises. Both run on **short-TTL child
branches** of `projects/capstone-pg`; **`production` is never modified**.

All scripts read `../../app/.env` and authenticate via its `DATABRICKS_PROFILE`.
Run as the project owner from a laptop:

```bash
cd lakebase/ops
uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv \
    python t9a_branch_pitr.py --keep      # T9a: branch + PITR
uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv \
    python t9b_query_insights.py --keep   # T9b: seq scan vs index
```

`--keep` leaves demo branches up so you can screenshot the Lakebase UI; omit it
(or delete-branch manually) to clean up. Branches carry a 4h TTL as a backstop.

| Script | Demonstrates | Screenshots |
|---|---|---|
| `t9a_branch_pitr.py` | copy-on-write branch, isolation, point-in-time recovery (`source_branch_time`) | branch creation; post-restore row count |
| `t9b_query_insights.py` | seq scan → index scan on `customer_audit_log(actor_email)`; before/after p95 | Query Performance row before vs. after index |

p95 is computed client-side from 100 timed runs (pg_stat_statements exposes
mean, not percentiles); the pg_stat_statements / Query-Performance row is the
screenshot artifact.
```

- [ ] **Step 2: Write `docs/t9-lakebase-ops-writeup.md`** — paste the actual captured numbers/plans from Task 2 & 3 runs and reference the screenshots.

```markdown
# T9 — Lakebase ops writeup

## T9a — Branch + PITR

- Project `capstone-pg` (Autoscaling, PG 16), 7-day history retention.
- Child branch `capstone-pitr-demo` created from `production` (copy-on-write).
  ![branch creation](img/t9a-branch-creation.png)
- `customer_notes_staging` on the branch: **N = <fill>** rows.
- `DELETE FROM customer_notes_staging` on the branch → 0 rows; `production`
  unchanged at **<fill>** rows (isolation proof — the app's live data is safe).
- PITR: `capstone-pitr-restored` created from the branch at T0 (before the
  delete) via `source_branch_time` → **<fill>** rows recovered (== N).
  ![post-restore row count](img/t9a-post-restore-count.png)

## T9b — Query insights

Query: `SELECT ... FROM customer_audit_log WHERE actor_email = 'perf500@example.com'`
on `capstone-perf-demo`, seeded with 200k rows across 1000 actor_emails.

| | p50 | p95 | p99 | plan |
|---|---|---|---|---|
| Before (no index) | <fill> | <fill> | <fill> | Seq Scan |
| After `CREATE INDEX ... (actor_email)` | <fill> | <fill> | <fill> | Index Scan |

![before](img/t9b-before.png) ![after](img/t9b-after.png)

Takeaway: the unindexed predicate forces a full sequential scan of the audit
log; a btree on `actor_email` turns it into an index scan, cutting p95 from
<fill> to <fill> ms.
```

- [ ] **Step 3: Fill every `<fill>` from the actual run output** (Task 2 & 3 stdout). No placeholders may remain.

- [ ] **Step 4: Commit**

```bash
cd /Users/johannes.gunther/sources/gdc-apps-lakebase-capstone
git add capstone-app/lakebase/ops/README.md capstone-app/docs/t9-lakebase-ops-writeup.md
git commit -m "docs(t9): ops runbook + branching/PITR + query-insight writeup"
```

---

## Self-Review

**Spec coverage:**
- T9a branch creation + isolation + PITR restore + screenshots → Task 2. ✓
- T9b 100× query, no-index slowness, CREATE INDEX, re-run, before/after p95 + screenshots → Task 3. ✓
- Script-what's-scriptable + runbook doc + writeup (graded artifact) → Tasks 1–4. ✓
- Production never touched destructively (child branches only) → enforced in Tasks 2/3. ✓
- Dedicated branch for T9b seeding → Task 3. ✓
- Client-side p95 (pg_stat_statements has no percentiles) → Task 1 `percentiles` + Task 3. ✓
- Stacked on `t5` → Global Constraints. ✓

**Placeholder scan:** The only `<fill>` markers are in the writeup template (Task 4 Step 2) and Task 4 Step 3 explicitly requires filling them from real output — not a plan placeholder. All code blocks are complete.

**Type consistency:** Helper names/signatures in Task 1 (`create_branch`, `readwrite_endpoint`, `endpoint_host`, `endpoint_token`, `connect`, `percentiles`, `current_user`, `load_cfg`) are used verbatim in Tasks 2 & 3. `create_branch` returns a branch path consumed by `readwrite_endpoint`/`delete_branch`. ✓
