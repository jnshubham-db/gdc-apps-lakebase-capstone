# T9 — Lakebase ops (branching + PITR, query insights) — design

**Date:** 2026-08-11
**Branch/PR:** `t9`, stacked on `t5` (PR base `t5`), matching the rest of the capstone stack.
**Task:** `CAPSTONE_TASKS.md` T9 (T9a Branch + PITR, T9b Query insights).

## Context

- Lakebase project: `projects/capstone-pg` (**Autoscaling**, PG 16, EU-central-1).
  - `production` branch, endpoint `primary`, DB `capstone_db`.
  - History retention `604800s` → **7-day PITR window**.
- Autoscaling supports **branching** (`databricks postgres create-branch`, CLI-scriptable)
  and **point-in-time recovery** (create/restore a branch at a past timestamp).
- `production` is the branch the **live deployed app** reads/writes. It must never be
  touched destructively.
- `customer_audit_log` today: **24 rows**; PK on `audit_id`, index on `customer_id`,
  **no index on `actor_email`** (the T9b target). Columns:
  `audit_id bigint PK, customer_id varchar(20), action varchar(50),
  actor_email varchar(320), payload jsonb, created_at timestamptz`.
- `customer_notes_staging`: 8 rows.
- `pg_stat_statements` is **available but not installed** (`CREATE EXTENSION` needed).
  It exposes `mean/min/max/stddev_exec_time` — **not true percentiles**, so a credible
  "p95" is computed **client-side** from the 100 timed runs; the `pg_stat_statements`
  row is captured as the Query-Performance screenshot.

## Guiding principles

- **Script what's scriptable; document the rest** (screenshots are the graded artifact).
- **Production is never touched destructively.** All destructive/seeding work runs on
  **throwaway child branches** of `capstone-pg`, deleted at the end.

## Deliverables

```
capstone-app/lakebase/ops/
  _common.py             # connect to an ARBITRARY branch endpoint (mint token + psycopg)
  t9a_branch_pitr.py     # driver: create branch → delete → PITR restore → print rowcounts
  t9b_query_insights.py  # driver: seed → 100× timed → p50/p95/p99 → CREATE INDEX → re-run
  README.md              # runbook: exact commands + where to click for each screenshot
docs/superpowers/specs/2026-08-11-t9-lakebase-ops-design.md   # this file
capstone-app/docs/t9-lakebase-ops-writeup.md                  # screenshots + before/after p95 (graded artifact)
```

### `lakebase/ops/_common.py`

- Loads `app/.env` (reuse the pattern from `lakebase/reverse_etl/_common.py`).
- `endpoint_host(profile, endpoint_path)` — `databricks postgres get-endpoint` → host.
- `endpoint_token(profile, endpoint_path)` — `databricks postgres generate-database-credential`
  → fresh OAuth token (endpoint path required, ~1h validity).
- `connect(host, user, dbname, token)` — psycopg connection, `sslmode=require`.
- User = current CLI user (`databricks current-user me`).

### T9a — `t9a_branch_pitr.py` (branch `capstone-pitr-demo`, child of `production`)

1. `create-branch` child `capstone-pitr-demo` from `projects/capstone-pg/branches/production`
   (short TTL, e.g. `"ttl": "14400s"`). → **Screenshot 1: branch creation** (Lakebase UI).
   Copy-on-write ⇒ starts with production's exact staging rows.
2. Connect to the branch endpoint. Record `T0` (after branch READY, before delete) and
   `N = count(customer_notes_staging)`.
3. `DELETE FROM customer_notes_staging` **on the branch** → 0 rows.
   Assert `production` count is **unchanged** (isolation proof).
4. **PITR restore** the branch to `T0`. Exact Autoscaling verb (a restore op vs.
   `create-branch` with a time spec, then read from the restored branch) confirmed at
   implementation time via `databricks postgres create-branch -h` / restore help; the
   driver prints the post-restore count. → count back to `N`.
   → **Screenshot 2: post-restore row count**.
5. Optional `--cleanup` flag: delete the demo branch(es) at the end.

### T9b — `t9b_query_insights.py` (branch `capstone-perf-demo`, separate child of `production`)

Dedicated branch so we never seed junk into production's audit log.

1. `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` (enable if the branch needs it).
2. **Seed** ~200k synthetic rows into `customer_audit_log` across ~1000 distinct
   `actor_email`s (batched `INSERT ... SELECT` / `generate_series`). Pick one target
   `actor_email` matching a moderate, selective slice (~200 rows).
3. Run `SELECT ... WHERE actor_email = :target` **100×**, timing each call → compute
   **p50/p95/p99** (before). Capture the `pg_stat_statements` row for the query
   (`mean_exec_time`, `calls`) → **before screenshot** (Query Performance UI).
4. `CREATE INDEX ON customer_audit_log (actor_email)`.
5. `SELECT pg_stat_statements_reset()`, re-run 100× → p50/p95/p99 (after) + **after
   screenshot**.
6. Print a before/after table (p50/p95/p99 + mean_exec_time) for the writeup.
   Optional `--cleanup` flag: delete the branch at the end.

### `capstone-app/docs/t9-lakebase-ops-writeup.md`

- T9a: screenshots of branch creation + post-restore row count; short narrative of the
  isolation + PITR demonstration.
- T9b: before/after p50/p95/p99 table, the `CREATE INDEX` statement, Query-Performance
  screenshots, and one-line takeaway (seq scan → index scan).

## Decisions

- **T9b on a dedicated branch** (not production): 200k seed rows in prod is undesirable;
  the `actor_email` index can be added to prod separately if wanted.
- **p95 computed client-side** from the 100 timed samples (pg_stat_statements has no
  percentiles); pg_stat_statements row used for the UI screenshot only.
- **Branches carry a short TTL** and an optional `--cleanup` flag so demo branches don't
  linger against the 10-branch project limit.

## Out of scope

- No app code changes (T9 is pure Lakebase ops).
- No permanent schema change to `production`.
- CI automation (consistent with the capstone's local inner-loop).

## Done when

- [ ] Screenshot of branch creation (T9a).
- [ ] Screenshot of post-restore row count matching pre-delete count (T9a).
- [ ] Before/after p95 recorded for the `actor_email` query, with the `CREATE INDEX`
      and Query-Performance screenshots (T9b).
- [ ] `lakebase/ops/` scripts run end-to-end from a laptop via the CLI profile.
- [ ] Writeup assembled in `capstone-app/docs/t9-lakebase-ops-writeup.md`.
