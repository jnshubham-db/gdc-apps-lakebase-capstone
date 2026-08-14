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
    print(
        f"  {label}: p50={p[50]:.2f}ms  p95={p[95]:.2f}ms  p99={p[99]:.2f}ms  (n={len(samples)})"
    )


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
    perf = c.create_branch(
        profile, PROJECT, PERF, source_branch=f"projects/{PROJECT}/branches/production"
    )
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
                cur.execute(
                    f"SELECT count(*) FROM {TABLE} WHERE actor_email = %s", (TARGET,)
                )
                print(f"  target '{TARGET}' matches {cur.fetchone()[0]} rows")
                cur.execute(f"ANALYZE {TABLE}")

                print("\n[before] EXPLAIN (no index):")
                print(_explain(cur))
                if has_pgss:
                    cur.execute("SELECT pg_stat_statements_reset()")
                _report("BEFORE", _timed_runs(cur, args.iters))

                print(
                    "\n[index] CREATE INDEX ON customer_audit_log (actor_email); ANALYZE"
                )
                cur.execute(
                    f"CREATE INDEX idx_audit_actor_email ON {TABLE} (actor_email)"
                )
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
                        print(
                            f"\n  pg_stat_statements (after): calls={row[0]} mean_exec_time={row[1]:.3f}ms"
                        )
    finally:
        if not args.keep:
            print("\ncleanup: deleting perf branch ...")
            c.delete_branch(profile, perf)
            print(f"    deleted {perf}")
        else:
            print("\n--keep set: leaving perf branch in place")


if __name__ == "__main__":
    main()
