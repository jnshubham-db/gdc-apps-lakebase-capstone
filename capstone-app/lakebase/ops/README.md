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
