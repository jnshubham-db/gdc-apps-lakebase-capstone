# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone 02 — Create the Lakebase Instance
# MAGIC
# MAGIC Provisions a Lakebase (managed Postgres) instance and registers it as a
# MAGIC Unity Catalog database catalog so it can be queried via federated SQL too.
# MAGIC
# MAGIC **Idempotent:** if an instance with the target name already exists, re-uses it.
# MAGIC
# MAGIC Run this AFTER `01_generate_gold_data.py`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("instance_name", "capstone-pg", "Lakebase instance name")
dbutils.widgets.text("uc_catalog_name", "capstone_lakebase", "UC catalog for Lakebase")
dbutils.widgets.text("capacity", "CU_1", "Lakebase capacity (CU_1, CU_2, CU_4, CU_8)")
dbutils.widgets.text("database_name", "capstone_db", "Postgres database name")

INSTANCE = dbutils.widgets.get("instance_name")
UC_CATALOG = dbutils.widgets.get("uc_catalog_name")
CAPACITY = dbutils.widgets.get("capacity")
DB_NAME = dbutils.widgets.get("database_name")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import DatabaseInstance, DatabaseCatalog

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md ## 1. Create / fetch the Lakebase instance

# COMMAND ----------

import time
from databricks.sdk.errors import NotFound

def _state_str(s) -> str:
    """Normalize state across SDK enum / string returns."""
    if s is None:
        return ""
    return getattr(s, "value", None) or str(s).split(".")[-1]

try:
    instance = w.database.get_database_instance(name=INSTANCE)
    print(f"Reusing existing instance: {INSTANCE} (state={_state_str(instance.state)})")
except NotFound:
    print(f"Creating instance {INSTANCE} ...")
    instance = w.database.create_database_instance(
        DatabaseInstance(name=INSTANCE, capacity=CAPACITY)
    )
    print(f"Created. (initial state may be empty until first GET)")

# Poll until AVAILABLE — typically 1-3 min on first create.
for i in range(60):
    try:
        instance = w.database.get_database_instance(name=INSTANCE)
    except NotFound:
        # Tiny propagation race right after create — keep waiting.
        time.sleep(5); continue
    state = _state_str(instance.state)
    if state == "AVAILABLE":
        break
    print(f"  state={state!r} — waiting 10s ...")
    time.sleep(10)
else:
    raise RuntimeError(f"Instance {INSTANCE} never became AVAILABLE")

print(f"Instance ready. read_write_dns={instance.read_write_dns}")

# COMMAND ----------

# MAGIC %md ## 2. Register Lakebase as a UC catalog (federated access)

# COMMAND ----------

# Requires CREATE CATALOG on the metastore. Skip cleanly if the user lacks it
# — federated SQL access is a *bonus*; the app can still talk to Lakebase
# directly via psycopg2.
from databricks.sdk.errors import PermissionDenied, NotFound as _NotFound
try:
    cat = w.database.get_database_catalog(name=UC_CATALOG)
    print(f"Reusing UC catalog: {UC_CATALOG}")
except _NotFound:
    try:
        cat = w.database.create_database_catalog(
            DatabaseCatalog(
                name=UC_CATALOG,
                database_instance_name=INSTANCE,
                database_name=DB_NAME,
                create_database_if_not_exists=True,
            )
        )
        print(f"Created UC catalog: {UC_CATALOG}")
    except PermissionDenied as e:
        print(f"SKIP UC catalog creation — no CREATE CATALOG on metastore: {e}")
        print("(Federated SQL queries from Delta to Lakebase will be unavailable; "
              "the rest of the capstone still works.)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Save outputs to a Databricks secret scope
# MAGIC
# MAGIC We store the connection host so subsequent notebooks + the app can read
# MAGIC it without hard-coding. The app itself will get the OBO/SP token at runtime
# MAGIC — we never store user PATs.

# COMMAND ----------

import os
USER = (spark.sql("SELECT current_user()").collect()[0][0]
        .split("@")[0].replace(".", "-"))
SCOPE = f"capstone-{USER}"

try:
    w.secrets.create_scope(scope=SCOPE)
    print(f"Created scope {SCOPE}")
except Exception:
    print(f"Scope {SCOPE} already exists")

w.secrets.put_secret(scope=SCOPE, key="pg_host", string_value=instance.read_write_dns)
w.secrets.put_secret(scope=SCOPE, key="pg_database", string_value=DB_NAME)
w.secrets.put_secret(scope=SCOPE, key="pg_instance_name", string_value=INSTANCE)
w.secrets.put_secret(scope=SCOPE, key="pg_uc_catalog", string_value=UC_CATALOG)

# COMMAND ----------

# MAGIC %md ## Save these into `app/.env`

# COMMAND ----------

print(f"PGHOST={instance.read_write_dns}")
print(f"PGDATABASE={DB_NAME}")
print(f"PG_INSTANCE_NAME={INSTANCE}")
print(f"PG_UC_CATALOG={UC_CATALOG}")
print(f"SECRET_SCOPE={SCOPE}")

# COMMAND ----------

# Structured output for the curl-installer (parsed via jobs.get_run_output)
import json
dbutils.notebook.exit(json.dumps({
    "PGHOST": instance.read_write_dns,
    "PGDATABASE": DB_NAME,
    "PG_INSTANCE_NAME": INSTANCE,
    "PG_UC_CATALOG": UC_CATALOG,
    "SECRET_SCOPE": SCOPE,
}))
