"""T1 — Create the Lakebase synced (reverse-ETL) tables.

Three read-optimised copies of gold Delta tables, kept fresh in Lakebase so
the app gets sub-10ms reads:

  * customers_synced     <- gold.customers      CONTINUOUS  (live profile/list)
  * transactions_synced  <- gold.transactions   CONTINUOUS  (live activity feed)
  * products_synced      <- gold.products       TRIGGERED   (hourly)

Why products is TRIGGERED, not CONTINUOUS: the product catalog is slow-changing
(200 rows, edited rarely), so a continuously-running sync pipeline would burn
DLT compute for almost no benefit. A periodic (e.g. hourly) refresh is well
within the freshness the UI needs and materially cheaper. customers/transactions
are CONTINUOUS because reps must see upstream changes (new signups, fresh
purchases) within seconds.

Note: a synced table has no built-in schedule field — TRIGGERED means "refresh
when the pipeline is triggered". To get an hourly cadence, schedule a refresh of
the generated sync pipeline (a Databricks Job on an hourly cron). That schedule
is left to the DABs job wiring (T8) rather than baked in here.

A synced table's id is `{catalog}.{schema}.{table}`, where `schema` names BOTH
the UC schema (a Lakehouse-Federation view is created there) and the Postgres
schema the table lands in. We target `{PG_UC_CATALOG}.public.*` so the synced
tables sit in Postgres `public` alongside the staging tables the app writes.
No dedicated Lakebase-backed "database catalog" is needed — a regular UC catalog
works; the synced table can even share the gold catalog. The `postgres_database`
field is what binds the UC entry to the Lakebase instance.

Prerequisites:
  * CDF enabled on the three source gold tables (required for TRIGGERED /
    CONTINUOUS). See enable_source_cdf.py.
  * UC schemas `{PG_UC_CATALOG}.public` (sync target) and
    `{PG_UC_CATALOG}.pipelines` (pipeline storage) exist. This script creates
    them if missing.

Drives the `databricks postgres create-synced-table` CLI (the supported path;
the old w.database SDK is the retired Provisioned API). Idempotent: skips a
table that already exists.

    uv run --with databricks-sdk --with python-dotenv \
        lakebase/reverse_etl/create_synced_tables.py
"""

from __future__ import annotations

import json
import subprocess
import sys

from databricks.sdk import WorkspaceClient

from _common import load_env

SYNC_SCHEMA = "public"  # UC + Postgres schema the synced tables land in
STORAGE_SCHEMA = "pipelines"  # UC schema for sync-pipeline metadata

# (postgres_table_name, source_gold_table, scheduling_policy, primary_key)
TABLES = [
    ("customers_synced", "customers", "CONTINUOUS", ["customer_id"]),
    ("transactions_synced", "transactions", "CONTINUOUS", ["transaction_id"]),
    ("products_synced", "products", "TRIGGERED", ["product_id"]),
]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _exists(profile: str, full_name: str) -> bool:
    r = _run(
        ["databricks", "postgres", "get-synced-table",
         f"synced_tables/{full_name}", "--profile", profile, "-o", "json"]
    )
    return r.returncode == 0


def _ensure_schema(w: WorkspaceClient, warehouse_id: str, catalog: str, schema: str) -> None:
    w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}",
        wait_timeout="30s",
    )


def main() -> None:
    cfg = load_env()
    profile = cfg["DATABRICKS_PROFILE"]
    catalog = cfg["PG_UC_CATALOG"]
    gold_catalog = cfg["CAPSTONE_CATALOG"]
    gold_schema = cfg.get("CAPSTONE_SCHEMA", "gold")
    project = cfg.get("PG_INSTANCE_NAME", "capstone-pg")
    branch = f"projects/{project}/branches/production"
    pg_database = cfg["PGDATABASE"]

    w = WorkspaceClient(profile=profile)
    for schema in (SYNC_SCHEMA, STORAGE_SCHEMA):
        _ensure_schema(w, cfg["WAREHOUSE_ID"], catalog, schema)

    for pg_name, source, policy, pk in TABLES:
        full_name = f"{catalog}.{SYNC_SCHEMA}.{pg_name}"
        if _exists(profile, full_name):
            print(f"  [skip] {full_name} already exists")
            continue

        spec: dict = {
            "source_table_full_name": f"{gold_catalog}.{gold_schema}.{source}",
            "primary_key_columns": pk,
            "scheduling_policy": policy,
            "branch": branch,
            "postgres_database": pg_database,
            "create_database_objects_if_missing": True,
            "new_pipeline_spec": {
                "storage_catalog": catalog,
                "storage_schema": STORAGE_SCHEMA,
            },
        }
        print(f"  [create] {full_name}  <-  {spec['source_table_full_name']}  ({policy})")
        r = _run(
            ["databricks", "postgres", "create-synced-table", full_name,
             "--json", json.dumps({"spec": spec}), "--profile", profile,
             "--no-wait", "-o", "json"]
        )
        if r.returncode != 0:
            sys.exit(f"    failed: {r.stderr.strip() or r.stdout.strip()}")
        print("    submitted (initial sync runs asynchronously)")

    print(
        "\nDone. Poll state with:\n"
        f"  databricks postgres get-synced-table "
        f"synced_tables/{catalog}.{SYNC_SCHEMA}.customers_synced --profile {profile}\n"
        "Synced tables reach CONTINUOUS / (TRIGGERED) after the first sync completes."
    )


if __name__ == "__main__":
    main()
