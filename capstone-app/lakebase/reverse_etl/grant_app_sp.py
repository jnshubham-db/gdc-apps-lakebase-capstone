"""T1 — Grant the app service principal access to synced + staging tables.

Fresh Postgres roles have no privileges. After the app is deployed (T8) and its
service principal has logged in to Lakebase at least once, its role exists —
named after the SP's client_id UUID. This one-time step grants that role:

  * SELECT on the synced tables (read-only serving copies)
  * SELECT / INSERT / UPDATE on the staging tables (the app writes notes,
    overrides, and audit rows)
  * USAGE on sequences (customer_audit_log.audit_id is a BIGSERIAL)
  * ALTER DEFAULT PRIVILEGES so future synced tables inherit SELECT — synced
    tables are (re)created by the sync pipeline, so their ownership/grants must
    not depend on this script running again.

Run as the project owner (schema owner), after deploy:

    uv run --with psycopg[binary] --with databricks-sdk --with python-dotenv \
        lakebase/reverse_etl/grant_app_sp.py <app-name>

If the SP role doesn't exist yet, load the app once so it connects to Lakebase,
then re-run.
"""

from __future__ import annotations

import sys

from databricks.sdk import WorkspaceClient
from psycopg import sql

from _common import connect, load_env, workspace_client

SYNCED_TABLES = ["customers_synced", "transactions_synced", "products_synced"]
STAGING_TABLES = [
    "customer_notes_staging",
    "customer_segment_overrides_staging",
    "customer_audit_log",
]


def _app_sp_client_id(w: WorkspaceClient, app_name: str) -> str:
    app = w.apps.get(name=app_name)
    client_id = getattr(app, "service_principal_client_id", None)
    if not client_id:
        sys.exit(f"App {app_name!r} has no service_principal_client_id yet.")
    return client_id


def _role_exists(cur, role: str) -> bool:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
    return cur.fetchone() is not None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: grant_app_sp.py <app-name>")
    app_name = sys.argv[1]

    cfg = load_env()
    w = workspace_client(cfg)
    role = _app_sp_client_id(w, app_name)
    role_ident = sql.Identifier(role)

    with connect(cfg, w) as conn:
        with conn.cursor() as cur:
            if not _role_exists(cur, role):
                sys.exit(
                    f"Postgres role {role!r} (app SP) does not exist yet. "
                    f"Load the app once so it connects to Lakebase, then re-run."
                )

            # Schema usage.
            cur.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_ident)
            )

            # Read-only on synced tables.
            for t in SYNCED_TABLES:
                cur.execute(
                    sql.SQL("GRANT SELECT ON {} TO {}").format(
                        sql.Identifier(t), role_ident
                    )
                )

            # Read/write on staging tables.
            for t in STAGING_TABLES:
                cur.execute(
                    sql.SQL("GRANT SELECT, INSERT, UPDATE ON {} TO {}").format(
                        sql.Identifier(t), role_ident
                    )
                )

            # Sequence usage (BIGSERIAL audit key, and any others).
            cur.execute(
                sql.SQL(
                    "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(role_ident)
            )

            # Future synced tables (recreated by the pipeline) inherit SELECT.
            # Default privileges are keyed on the granting role; synced tables
            # are owned by the pipeline identity, so we set it for both the
            # current user and broadly on the schema.
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT ON TABLES TO {}"
                ).format(role_ident)
            )
        conn.commit()

    print(f"Granted app SP role {role!r}:")
    print(f"  SELECT on synced: {', '.join(SYNCED_TABLES)}")
    print(f"  SELECT/INSERT/UPDATE on staging: {', '.join(STAGING_TABLES)}")
    print("  USAGE on schema + sequences; default SELECT on future tables.")


if __name__ == "__main__":
    main()
