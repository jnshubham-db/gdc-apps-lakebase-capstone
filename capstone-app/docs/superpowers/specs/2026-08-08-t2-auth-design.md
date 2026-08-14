# T2 — Auth: OBO and service-principal clients

## Goal

Give the app two identities and a Lakebase connection helper:

- **OBO** (on-behalf-of) — carries the *calling user's* identity to SQL
  warehouse + Genie, so workspace RLS and audit attribute to the human.
- **SP** (service principal) — app-level identity for all Lakebase access
  and the forward-ETL job trigger. Not tied to a user.
- **`lakebase_sp()`** — a psycopg connection helper that always talks to
  Lakebase as the SP, minting fresh ~1h OAuth tokens.

Prescribed by `CAPSTONE_TASKS.md` T2. This spec fills the seams the task
leaves open: local-vs-deployed identity, token lifecycle, actor capture.

## Modules

Three files under `app/backend/`.

### `config.py` (new, small)

`load_env() -> dict[str,str]` — the app-runtime analogue of the T1
`lakebase/reverse_etl/_common.py` loader:

- Read `app/.env` via `dotenv_values` for local dev.
- **Real `os.environ` wins** where set — the deployed runtime injects
  `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `LAKEBASE_ENDPOINT`, and SP
  OAuth creds; those must override any stale `.env` value.
- `deployed() -> bool` predicate: true when SP creds are injected
  (`DATABRICKS_CLIENT_ID` in `os.environ`). Drives the fallbacks below.

Keeps dotenv/path logic out of `auth.py` and `db.py`.

### `auth.py`

- `sp_client() -> WorkspaceClient` — module-level singleton (lazy).
  - Deployed: bare `WorkspaceClient()` — picks up injected SP creds.
  - Local: `WorkspaceClient(profile=<DATABRICKS_PROFILE>)` — connects as
    the developer. (Chosen fallback: lets all three done-checks be
    verified locally before the app SP exists.)
- `obo_client(request) -> WorkspaceClient` — read `X-Forwarded-Access-Token`
  and return `WorkspaceClient(host=..., token=<that>)`. Raise a clear
  error if the header is absent (OBO preview off / consent not granted).
  Used for SQL warehouse + Genie **only**.
- `actor_email(request) -> str` — read `X-Forwarded-Email` for the audit
  trail; local fallback to `sp_client().current_user.me().user_name`.
- **No `lakebase_obo()`.** Documented inline: Lakebase rejects a user OBO
  bearer with `Provided OAuth token does not have required scopes:
  postgres`. All DB access is SP; the human is recorded via `actor_email`.
- OBO scopes for this capstone: exactly `sql` and `dashboards.genie`.

### `db.py`

- Module-level `psycopg_pool.ConnectionPool`, lazily initialised on first
  `lakebase_sp()` call (import must not require connectivity).
- `connection`-open callback mints a **fresh** OAuth token via
  `sp_client().postgres.generate_database_credential(endpoint=<LAKEBASE_ENDPOINT>)`
  each time a physical connection opens.
- `sslmode=require`; `max_lifetime ≈ 45 min` so connections recycle before
  the ~1h token expires; `check`/pre-ping to survive scale-to-zero wake-up.
- Connection params: `host=PGHOST`, `port=PGPORT|5432`, `dbname=PGDATABASE`,
  `user=PGUSER` deployed / `w.current_user.me().user_name` local.
- `lakebase_sp()` — `@contextmanager` yielding a pooled connection:
  `with lakebase_sp() as conn: ...`.

### Endpoint path resolution

`generate_database_credential` needs the endpoint resource path.

- Deployed: `os.environ["LAKEBASE_ENDPOINT"]`.
- Local: add `LAKEBASE_ENDPOINT` to `app/.env` as the source of truth,
  derived from `PG_INSTANCE_NAME`:
  `projects/<PG_INSTANCE_NAME>/branches/production/endpoints/primary`.

## Verification (Done-when)

Scratch script `app/backend/_t2_smoke.py` (run locally, **not committed** —
gitignored or removed after):

1. `sp_client().current_user.me()` → prints the identity (locally = you;
   deployed audit logs = the SP). ✔ done-check 2.
2. `SELECT 1` via `lakebase_sp()` → returns `1`. ✔ done-check 3.
3. `obo_client` — cannot be exercised locally (no forwarded headers).
   Verify by constructing a fake request carrying `X-Forwarded-Access-Token`
   and asserting the token is read into the client config. **Real
   end-to-end OBO (calling user ≠ SP) waits for T8 deploy** — noted as a
   known gap, not a silent skip. ✔ done-check 1 (structurally).

## Out of scope

- App deployment / `app.yaml` / `user_api_scopes` wiring — T6/T8.
- `grant_app_sp.py` run — needs the deployed SP role (T8).
- Any API endpoints that *use* these clients — T3.
