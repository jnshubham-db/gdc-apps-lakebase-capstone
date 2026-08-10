# Databricks notebook source
# MAGIC %md
# MAGIC # Forward ETL (Pattern A) — drain Lakebase staging into Delta gold
# MAGIC
# MAGIC Reads unprocessed rows from the app's Lakebase staging tables, MERGEs
# MAGIC them into gold, then flips `processed=true` for that exact ID set.
# MAGIC
# MAGIC **Ordering is MERGE-first, flip-after.** True cross-system atomicity is
# MAGIC impossible (Spark/Delta vs Postgres/Lakebase are separate systems). Delta
# MAGIC is the source of truth; a crash between MERGE and flip re-MERGEs the same
# MAGIC rows next run — harmless because the MERGE keys on the PK. The reverse
# MAGIC order could silently lose rows, so it is never used.

# COMMAND ----------

import os

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2.extras import RealDictCursor


def _cfg(widget, env, default=""):
    try:
        return dbutils.widgets.get(widget)  # noqa: F821 - dbutils provided by Databricks runtime
    except Exception:  # noqa: BLE001 — widget not found outside notebook runtime
        return os.environ.get(env, default)


CATALOG = _cfg("catalog", "CAPSTONE_CATALOG")
PGHOST = _cfg("pghost", "PGHOST")
PGDATABASE = _cfg("pgdatabase", "PGDATABASE")
GOLD = f"{CATALOG}.gold"

# COMMAND ----------

# MAGIC %md ## Gold DDL — self-contained on first run

# COMMAND ----------

spark.sql(  # noqa: F821 - spark provided by Databricks notebook runtime
    f"""
CREATE TABLE IF NOT EXISTS {GOLD}.customer_notes (
    note_id       STRING,
    customer_id   STRING,
    author_email  STRING,
    note_text     STRING,
    created_at    TIMESTAMP
) USING DELTA
"""
)

spark.sql(  # noqa: F821 - spark provided by Databricks notebook runtime
    f"""
CREATE TABLE IF NOT EXISTS {GOLD}.customer_segment_overrides (
    customer_id      STRING,
    override_segment STRING,
    reason           STRING,
    author_email     STRING,
    updated_at       TIMESTAMP
) USING DELTA
"""
)

# COMMAND ----------

# MAGIC %md ## Lakebase connection (SP OAuth token, sslmode=require)

# COMMAND ----------


def lakebase_conn():
    """psycopg2 connection as the job run-as identity (fresh OAuth token).

    psycopg2-binary is the Databricks-standard Postgres driver on serverless;
    psycopg3's ``[binary]`` wheel SIGABRTs loading its bundled libpq there.
    """
    w = WorkspaceClient()
    token = w.config.oauth_token().access_token
    user = w.current_user.me().user_name
    return psycopg2.connect(
        host=PGHOST,
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=PGDATABASE,
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )


# COMMAND ----------

# MAGIC %md ## Drain — snapshot → MERGE → flip

# COMMAND ----------


def drain(conn, *, table, pk, gold_table, select_cols, merge_on, cast) -> int:
    """Drain one staging table into its gold target. Returns rows drained."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT {select_cols} FROM {table} WHERE processed = false")
        rows = cur.fetchall()
    if not rows:
        return 0

    # str() the ids so the flip binds text[] against a `{pk}::text` cast — works
    # whether the driver returns the UUID pk as uuid.UUID (psycopg3) or str (psycopg2).
    ids = [str(r[pk]) for r in rows]
    # UUID/JSON → strings so Spark can infer a clean schema.
    df = spark.createDataFrame([cast(r) for r in rows])  # noqa: F821 - spark provided by Databricks notebook runtime
    view = f"_stage_{table}"
    df.createOrReplaceTempView(view)
    spark.sql(  # noqa: F821 - spark provided by Databricks notebook runtime
        f"""
        MERGE INTO {gold_table} t USING {view} s ON {merge_on}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """
    )

    # Flip only AFTER the MERGE committed, for the exact snapshotted id set.
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET processed = true, processed_at = NOW() "
            f"WHERE {pk}::text = ANY(%s)",
            (ids,),
        )
    conn.commit()
    return len(ids)


# COMMAND ----------


def _cast_note(r: dict) -> dict:
    return {
        "note_id": str(r["note_id"]),
        "customer_id": r["customer_id"],
        "author_email": r["author_email"],
        "note_text": r["note_text"],
        "created_at": r["created_at"],
    }


def _cast_override(r: dict) -> dict:
    return {
        "customer_id": r["customer_id"],
        "override_segment": r["override_segment"],
        "reason": r["reason"],
        "author_email": r["author_email"],
        "updated_at": r["updated_at"],
    }


# COMMAND ----------

with lakebase_conn() as conn:
    n_notes = drain(
        conn,
        table="customer_notes_staging",
        pk="note_id",
        gold_table=f"{GOLD}.customer_notes",
        select_cols="note_id, customer_id, author_email, note_text, created_at",
        merge_on="t.note_id = s.note_id",
        cast=_cast_note,
    )
    n_over = drain(
        conn,
        table="customer_segment_overrides_staging",
        pk="override_id",
        gold_table=f"{GOLD}.customer_segment_overrides",
        select_cols=(
            "override_id, customer_id, override_segment, reason, "
            "author_email, updated_at"
        ),
        merge_on="t.customer_id = s.customer_id",
        cast=_cast_override,
    )

print(f"notes drained: {n_notes}")
print(f"overrides drained: {n_over}")
