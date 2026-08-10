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
