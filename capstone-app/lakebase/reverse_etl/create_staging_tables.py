"""T1 — Create the writable staging tables in Lakebase.

Three tables the app writes to (via the app SP, T3) and the forward-ETL job
drains (T7):

  * ``customer_notes_staging``              — free-text notes; ``processed`` flag
  * ``customer_segment_overrides_staging``  — one override per customer (UPSERT); ``processed`` flag
  * ``customer_audit_log``                  — append-only record of every write

Idempotent: uses ``CREATE TABLE IF NOT EXISTS`` throughout, so re-running is a
no-op. Run as the project owner:

    uv run --with psycopg[binary] --with databricks-sdk --with python-dotenv \
        lakebase/reverse_etl/create_staging_tables.py

Needs no Lakebase UC catalog — these are plain Postgres tables in
``capstone_db``.
"""

from __future__ import annotations

from _common import connect, load_env, workspace_client

# pgcrypto gives us gen_random_uuid() for surrogate keys.
DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Notes: append-only from the app's perspective; forward-ETL flips `processed`.
CREATE TABLE IF NOT EXISTS customer_notes_staging (
    note_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id  VARCHAR(20)  NOT NULL,
    author_email VARCHAR(320) NOT NULL,
    note_text    TEXT         NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed    BOOLEAN      NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notes_customer
    ON customer_notes_staging (customer_id);
-- Partial index: the forward-ETL job only ever scans unprocessed rows.
CREATE INDEX IF NOT EXISTS idx_notes_unprocessed
    ON customer_notes_staging (processed) WHERE processed = FALSE;

-- Segment overrides: at most one active override per customer, so the app can
-- UPSERT on customer_id (ON CONFLICT) and re-submitting the same value is a
-- no-op rather than a duplicate row (T3 idempotency requirement).
CREATE TABLE IF NOT EXISTS customer_segment_overrides_staging (
    override_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id      VARCHAR(20)  NOT NULL UNIQUE,
    override_segment VARCHAR(10)  NOT NULL,
    reason           TEXT,
    author_email     VARCHAR(320) NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed        BOOLEAN      NOT NULL DEFAULT FALSE,
    processed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_overrides_unprocessed
    ON customer_segment_overrides_staging (processed) WHERE processed = FALSE;

-- Audit log: append-only. Every note/override write appends one row in the
-- same transaction as the write (T3). BIGSERIAL gives a monotonic key.
CREATE TABLE IF NOT EXISTS customer_audit_log (
    audit_id    BIGSERIAL    PRIMARY KEY,
    customer_id VARCHAR(20)  NOT NULL,
    action      VARCHAR(50)  NOT NULL,
    actor_email VARCHAR(320) NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_customer
    ON customer_audit_log (customer_id);
"""

EXPECTED = {
    "customer_notes_staging",
    "customer_segment_overrides_staging",
    "customer_audit_log",
}


def main() -> None:
    cfg = load_env()
    w = workspace_client(cfg)
    with connect(cfg, w) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
            present = {row[0] for row in cur.fetchall()}

    print(f"Connected to {cfg['PGHOST']} / {cfg['PGDATABASE']}")
    for name in sorted(EXPECTED):
        print(f"  [{'ok' if name in present else 'MISSING'}] public.{name}")
    missing = EXPECTED - present
    if missing:
        raise SystemExit(f"Staging tables missing after DDL: {', '.join(sorted(missing))}")
    print("All staging tables present.")


if __name__ == "__main__":
    main()
