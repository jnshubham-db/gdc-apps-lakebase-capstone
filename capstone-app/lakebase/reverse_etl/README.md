# T1 — Reverse ETL: synced + staging tables

Wires the two Lakebase data paths the app needs:

- **Synced tables** — read-optimised copies of gold Delta tables, kept fresh in
  Lakebase for sub-10ms reads.
- **Staging tables** — writable Postgres tables the app writes notes / segment
  overrides / audit rows into (drained back to gold by the forward-ETL job, T7).

All scripts read config from `../../app/.env` and authenticate via the
`DATABRICKS_PROFILE` there. Run them as the **project owner** from a laptop; the
deployed app connects as its own service principal (T2), not through these.

## Scripts

| Script | What it does | Needs |
|---|---|---|
| `enable_source_cdf.py` | Enables Change Data Feed on `gold.{customers,transactions,products}` (required for TRIGGERED/CONTINUOUS sync). | warehouse |
| `create_staging_tables.py` | Creates the 3 writable staging tables + indexes in `capstone_db`. | Lakebase connect |
| `create_synced_tables.py` | Creates the 3 synced tables (2× CONTINUOUS, 1× TRIGGERED) in `{PG_UC_CATALOG}.public`. Creates the `public` + `pipelines` UC schemas if missing. | warehouse |
| `grant_app_sp.py <app-name>` | Grants the app SP role SELECT on synced + SELECT/INSERT/UPDATE on staging. **Run after the app is deployed (T8).** | deployed app |

Each is idempotent — safe to re-run.

### On the UC catalog

A synced table's id is `{catalog}.{schema}.{table}`, where `schema` is **both**
the UC schema (a federation view is created there) and the Postgres schema the
table lands in. We use `{PG_UC_CATALOG}.public.*` so synced tables sit in
Postgres `public` next to the staging tables.

No dedicated Lakebase-backed "database catalog" is required — a regular UC
catalog works, and here `PG_UC_CATALOG` is simply the gold catalog
(`test_jg_catalog`). What binds the UC entry to the Lakebase instance is the
`postgres_database` field on the sync spec, not the catalog type. The only
prerequisite is that the target UC schema exists (the script creates it).

## Order of operations

```
1. enable_source_cdf.py          # once; independent of everything else
2. create_staging_tables.py      # writable Postgres tables
3. create_synced_tables.py       # synced tables into {PG_UC_CATALOG}.public
   -- deploy the app (T8) --
4. grant_app_sp.py <app-name>    # needs the app SP role to exist in Postgres
```

## Run

```bash
cd lakebase/reverse_etl
uv run --with "psycopg[binary]" --with databricks-sdk --with python-dotenv \
    python create_staging_tables.py
```

## Sync-mode reflection

| Synced table | Source | Mode | Rationale |
|---|---|---|---|
| `customers_synced` | `gold.customers` | **CONTINUOUS** | Reps must see new signups / churn-score / segment changes within seconds. |
| `transactions_synced` | `gold.transactions` | **CONTINUOUS** | The activity feed should reflect fresh purchases live. |
| `products_synced` | `gold.products` | **TRIGGERED** | The 200-row catalog is slow-changing; a continuous pipeline would burn DLT compute for near-zero benefit. An hourly refresh is fresh enough and materially cheaper. |

A synced table has **no built-in schedule** — TRIGGERED means "refresh when the
pipeline is triggered". The hourly cadence for `products_synced` is applied by
scheduling a refresh of its generated sync pipeline via a Databricks Job
(wired in the bundle, T8), not as a property of the synced table.

## Verify (Done-when)

- Synced tables reach `CONTINUOUS` / `TRIGGERED` state:
  ```bash
  databricks postgres get-synced-table \
    synced_tables/test_jg_catalog.public.customers_synced --profile <profile>
  ```
- Staging tables exist with the right columns (via `psql` / `\dt`), or re-run
  `create_staging_tables.py` — it prints a per-table check.
