"""T1 (prerequisite) — Enable Change Data Feed on the gold source tables.

TRIGGERED and CONTINUOUS synced tables require CDF on their Delta source. This
enables it on the three tables that get synced. Idempotent — setting the
property when already set is a no-op.

    uv run --with databricks-sdk --with python-dotenv \
        lakebase/reverse_etl/enable_source_cdf.py
"""

from __future__ import annotations

from databricks.sdk import WorkspaceClient

from _common import load_env

SOURCES = ["customers", "transactions", "products"]


def main() -> None:
    cfg = load_env()
    w = WorkspaceClient(profile=cfg["DATABRICKS_PROFILE"])
    warehouse_id = cfg["WAREHOUSE_ID"]
    catalog = cfg["CAPSTONE_CATALOG"]
    schema = cfg.get("CAPSTONE_SCHEMA", "gold")

    for table in SOURCES:
        fqn = f"{catalog}.{schema}.{table}"
        w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=(
                f"ALTER TABLE {fqn} "
                f"SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
            ),
            wait_timeout="30s",
        )
        print(f"  [ok] CDF enabled on {fqn}")

    print("Change Data Feed enabled on all source tables.")


if __name__ == "__main__":
    main()
