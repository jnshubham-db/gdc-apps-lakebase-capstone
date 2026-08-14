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
import json
import time
from datetime import UTC, datetime

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


def _cleanup(profile: str, branches: list[str]) -> None:
    """Best-effort teardown (child before parent); tolerate a branch not existing."""
    print("\ncleanup: deleting demo branches ...")
    for b in branches:
        try:
            c.delete_branch(profile, b)
            print(f"    deleted {b}")
        except Exception as e:  # noqa: BLE001 — teardown must not mask the real error; branch may not exist
            print(f"    skip {b}: {e}")


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
    # Use no_expiry=true so PITR can later create a child from this branch.
    # c.create_branch always sets TTL; the API rejects "child of TTL branch", so
    # we call c.cli_json directly here.
    c.cli_json(
        "postgres",
        "create-branch",
        f"projects/{PROJECT}",
        DEMO,
        "--json",
        json.dumps({"spec": {"source_branch": prod, "no_expiry": True}}),
        "--replace-existing",
        profile=profile,
    )
    demo = f"projects/{PROJECT}/branches/{DEMO}"
    print(f"    created {demo}   <-- screenshot 1: branch creation (Lakebase UI)")

    # Demo branch exists now: wrap the rest so the finally always tears the demo
    # branches down. The demo branch is no_expiry, so a failure here (e.g. a
    # failed assert) would otherwise leave it running indefinitely.
    restored = None
    try:
        n = _count(profile, demo, cfg, user)
        print(f"[2] {DEMO} {STAGING} rows: {n}")
        time.sleep(
            20
        )  # ensure T0 is safely after branch creation / WAL settle (increased from 5s after PITR "too recent" error)
        t0 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        restored = c.create_branch(
            profile, PROJECT, RESTORED, source_branch=demo, source_branch_time=t0
        )
        restored_n = _count(profile, restored, cfg, user)
        print(
            f"    {RESTORED} {STAGING} rows: {restored_n}   <-- screenshot 2: post-restore row count"
        )
        assert restored_n == n, f"PITR restored {restored_n}, expected {n}"
        print(f"    PITR OK — recovered {restored_n} rows deleted on {DEMO}")
    finally:
        if args.keep:
            print("\n--keep set: leaving demo branches in place (delete manually later)")
        else:
            # child (restored) before parent (demo); restored may not exist on early failure
            _cleanup(profile, [b for b in (restored, demo) if b])


if __name__ == "__main__":
    main()
