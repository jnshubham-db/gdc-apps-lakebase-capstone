# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone 03 — Synced (read) tables + Staging (write) tables
# MAGIC
# MAGIC Two sets of Lakebase objects:
# MAGIC
# MAGIC 1. **Synced tables** — auto-refreshed copies of UC Delta tables. The app
# MAGIC    reads these for sub-10ms latency.
# MAGIC    - `customers_synced`     (CONTINUOUS — live updates)
# MAGIC    - `transactions_synced`  (CONTINUOUS — recent activity feed)
# MAGIC    - `products_synced`      (TRIGGERED hourly — slow-changing)
# MAGIC
# MAGIC 2. **Staging tables** — written by the app via psycopg2. Forward-ETL job
# MAGIC    reads these and MERGEs into Delta gold.
# MAGIC    - `customer_notes_staging`
# MAGIC    - `customer_segment_overrides_staging`
# MAGIC    - `customer_audit_log`
# MAGIC
# MAGIC Run AFTER notebook 02.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk psycopg2-binary

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "capstone", "Source UC catalog (gold tables)")
dbutils.widgets.text("schema", "gold", "Source schema")
dbutils.widgets.text("uc_lakebase_catalog", "capstone_lakebase", "UC catalog backed by Lakebase")
dbutils.widgets.text("instance_name", "capstone-pg", "Lakebase instance name")
dbutils.widgets.text("database_name", "capstone_db", "Postgres database name")
dbutils.widgets.text("storage_catalog", "capstone", "Catalog for sync pipeline storage")
dbutils.widgets.text("storage_schema", "pipelines", "Schema for sync pipeline storage")

CAT = dbutils.widgets.get("catalog")
SCH = dbutils.widgets.get("schema")
LB_CAT = dbutils.widgets.get("uc_lakebase_catalog")
INSTANCE = dbutils.widgets.get("instance_name")
DB_NAME = dbutils.widgets.get("database_name")
STORAGE_CAT = dbutils.widgets.get("storage_catalog")
STORAGE_SCH = dbutils.widgets.get("storage_schema")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {STORAGE_CAT}.{STORAGE_SCH}")

# COMMAND ----------

# MAGIC %md ## 1. Create synced tables (reverse ETL)

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable, SyncedTableSpec, NewPipelineSpec,
    SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

def sync(name: str, source_table: str, mode: SyncedTableSchedulingPolicy, pk: list[str]):
    full_name = f"{LB_CAT}.public.{name}"
    try:
        existing = w.database.get_synced_database_table(name=full_name)
        print(f"  reusing {full_name} (state={existing.data_synchronization_status})")
        return existing
    except Exception:
        pass
    spec = SyncedTableSpec(
        source_table_full_name=source_table,
        primary_key_columns=pk,
        scheduling_policy=mode,
        new_pipeline_spec=NewPipelineSpec(
            storage_catalog=STORAGE_CAT,
            storage_schema=STORAGE_SCH,
        ),
    )
    return w.database.create_synced_database_table(
        SyncedDatabaseTable(name=full_name, spec=spec)
    )

sync("customers_synced",
     f"{CAT}.{SCH}.customers",
     SyncedTableSchedulingPolicy.CONTINUOUS,
     ["customer_id"])
sync("transactions_synced",
     f"{CAT}.{SCH}.transactions",
     SyncedTableSchedulingPolicy.CONTINUOUS,
     ["transaction_id"])
sync("products_synced",
     f"{CAT}.{SCH}.products",
     SyncedTableSchedulingPolicy.TRIGGERED,
     ["product_id"])

print("Synced tables submitted. Initial sync may take a few minutes.")

# COMMAND ----------

# MAGIC %md ## 2. Create staging tables in Lakebase via psycopg2
# MAGIC
# MAGIC Uses an OAuth token (current user identity) to connect.

# COMMAND ----------

import psycopg2

instance = w.database.get_database_instance(name=INSTANCE)
host = instance.read_write_dns
me = spark.sql("SELECT current_user()").collect()[0][0]
token = w.config.oauth_token().access_token

conn = psycopg2.connect(
    host=host, port=5432, dbname=DB_NAME,
    user=me, password=token, sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS customer_notes_staging (
    note_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id    VARCHAR(20)  NOT NULL,
    author_email   VARCHAR(200) NOT NULL,
    note_text      TEXT         NOT NULL,
    sentiment      REAL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed      BOOLEAN      NOT NULL DEFAULT FALSE,
    processed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notes_customer ON customer_notes_staging (customer_id);
CREATE INDEX IF NOT EXISTS idx_notes_unprocessed ON customer_notes_staging (processed) WHERE processed = FALSE;

CREATE TABLE IF NOT EXISTS customer_segment_overrides_staging (
    override_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      VARCHAR(20)  NOT NULL UNIQUE,
    override_segment VARCHAR(10)  NOT NULL,
    reason           TEXT,
    author_email     VARCHAR(200) NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed        BOOLEAN      NOT NULL DEFAULT FALSE,
    processed_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS customer_audit_log (
    audit_id     BIGSERIAL    PRIMARY KEY,
    customer_id  VARCHAR(20)  NOT NULL,
    action       VARCHAR(50)  NOT NULL,
    actor_email  VARCHAR(200) NOT NULL,
    payload      JSONB,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_customer ON customer_audit_log (customer_id);
"""
cur.execute(DDL)

# Show the resulting object list
cur.execute("""
    SELECT schemaname, tablename FROM pg_tables
    WHERE schemaname = 'public' ORDER BY tablename
""")
for s, t in cur.fetchall():
    print(f"  {s}.{t}")

cur.close()
conn.close()

# COMMAND ----------

print("Lakebase schema ready.")
print(f"PG_HOST={host}")
print(f"PG_DATABASE={DB_NAME}")
