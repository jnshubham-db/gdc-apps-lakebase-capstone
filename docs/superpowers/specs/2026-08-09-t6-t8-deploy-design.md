# T6 + T8 — app.yaml + DABs git-source deploy (dev) — design

**Date:** 2026-08-09
**Tasks:** CAPSTONE_TASKS.md T6 (app.yaml) + T8 (DABs git-source app; local deploy/run)
**Stacked on:** t5 → t4 → t3-frontend → t3-backend → …
**Deploy target:** dev, git-source app tracking the **`t5`** branch on `fevm-test-jg`.

## Goal

Ship the Customer 360 app to Databricks Apps as a **git-source app** deployed via
DABs (`bundle deploy` + `bundle run`), with `app.yaml` wiring runtime config and
OBO scopes. Dev target; the app pulls source from the GitHub repo's `t5` branch.

## Decisions (locked in brainstorm)

- **Bundle scope:** app + its resources only. No `resources/jobs.yml` (T7 forward-ETL
  not built) and no `resources/lakebase.yml` (T1 synced tables already exist manually;
  re-declaring risks drift). `FORWARD_ETL_JOB_ID` env omitted until T7.
- **Env wiring:** static values from `app/.env` written directly into `app/app.yaml`
  `env`. SP creds (`DATABRICKS_CLIENT_ID/SECRET`) + `DATABRICKS_HOST` are injected by
  the Apps runtime — not listed. No secret-scope `valueFrom` (these ids aren't secret).
- **Frontend dist:** built locally and **committed on the `t5` branch only**
  (force-added; stays gitignored on every other branch so it never pollutes main /
  feature history). Runtime command is a clean `uvicorn` with no build step. This is
  the least-ugly way to satisfy T8's "commit dist so the runtime command needs no
  build" under the git-source constraint (a git-source app can only serve what's
  committed).
- **SP git credential:** the git-source pull runs as the app's SP. When the pull needs
  a GitHub credential, the user provides a PAT at deploy time (or runs
  `git-credentials create --json {... principal_id: <APP_SP_ID> ...}` themselves).
- **Runtime:** non-AppKit FastAPI app. `pyproject.toml` at `capstone-app/app/` root →
  runtime detects Python (not Node); no root `package.json` to trigger a failing npm
  build. Serve on `--host 0.0.0.0 --port 8000`.

## T6 — `capstone-app/app/app.yaml`

```yaml
command:
  - "uvicorn"
  - "backend.main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - { name: "PGHOST",            value: "ep-billowing-cake-d7ma4pcu.database.eu-central-1.cloud.databricks.com" }
  - { name: "PGDATABASE",        value: "capstone_db" }
  - { name: "LAKEBASE_ENDPOINT", value: "projects/capstone-pg/branches/production/endpoints/primary" }
  - { name: "WAREHOUSE_ID",      value: "e31f5efacda6d932" }
  - { name: "DASHBOARD_ID",      value: "01f19331dc2e190cbba8dc3f1cbe1c26" }
  - { name: "GENIE_SPACE_ID",    value: "01f19331ffeb16119db5afb749349f4c" }
  - { name: "CAPSTONE_CATALOG",  value: "test_jg_catalog" }
  - { name: "CAPSTONE_SCHEMA",   value: "gold" }
  - { name: "PG_UC_CATALOG",     value: "test_jg_catalog" }
```

- `config.py` reads these into `Settings`; presence of runtime-injected
  `DATABRICKS_CLIENT_ID` flips `Settings.deployed` → True (SP auth path).
- No `.env` ships (gitignored) — env is the sole config source on the deployed app.
- **OBO scopes are NOT in app.yaml** — they live in the DABs app resource
  (`user_api_scopes`, see below), per T6/T8.

## T8 — DABs bundle (repo root)

### `databricks.yml`
```yaml
bundle:
  name: customer360

include:
  - resources/*.yml

variables:
  warehouse_id:     { default: "e31f5efacda6d932" }
  dashboard_id:     { default: "01f19331dc2e190cbba8dc3f1cbe1c26" }
  genie_space_id:   { default: "01f19331ffeb16119db5afb749349f4c" }
  catalog:          { default: "test_jg_catalog" }
  pg_uc_catalog:    { default: "test_jg_catalog" }
  lakebase_instance:{ default: "capstone-pg" }
  git_repo_url:     { default: "https://github.com/jogueber/gdc-apps-lakebase-capstone" }
  git_branch:       { default: "t5" }

targets:
  dev:
    default: true
    mode: development
    workspace:
      host: https://fevm-test-jg.cloud.databricks.com
  prod:
    mode: production
    workspace:
      host: https://fevm-test-jg.cloud.databricks.com
    variables:
      git_branch: "main"
```

(Profile is passed via `--profile fevm-test-jg` on the CLI, not pinned in the file, to
match the project's never-hardcode-profile convention.)

### `resources/app.yml` — git-source app
```yaml
resources:
  apps:
    customer360:
      name: "customer360-dev"          # ≤26 chars, lowercase+hyphens; dev target
      description: "Customer 360 — Acme Retail (capstone)"
      # NO app-level source_code_path — git-source apps use git_repository +
      # git_source instead; DABs rejects setting both.
      git_repository:
        provider: gitHub                        # required; case-insensitive
        url: ${var.git_repo_url}                 # required
      git_source:
        branch: ${var.git_branch}
        source_code_path: capstone-app/app     # path INSIDE the repo
      user_api_scopes:
        - sql
        - dashboards.genie
      resources:
        - name: sql-warehouse
          sql_warehouse:
            id: ${var.warehouse_id}
            permission: "CAN_USE"
        - name: database
          postgres:                              # NOT the legacy `database` key
            branch: "projects/capstone-pg/branches/production"
            # resource id is a hashed name, NOT "capstone_db" (that's the PG db name);
            # confirmed: db-dq3m-k807y4emil → postgres_database "capstone_db"
            database: "projects/capstone-pg/branches/production/databases/db-dq3m-k807y4emil"
            permission: "CAN_CONNECT_AND_CREATE"
        - name: genie-space
          genie_space:
            space_id: ${var.genie_space_id}
            permission: "CAN_RUN"
```

> **Resource keys (from the DABs Apps resource reference):** `sql_warehouse`
> = `{ id, permission: CAN_USE }`; `genie_space` = `{ space_id, permission: CAN_RUN }`.
> For Lakebase use the **`postgres`** key = `{ branch, database, permission:
> CAN_CONNECT_AND_CREATE }` with full resource paths — NOT the legacy `database` key
> (`instance_name`+`database_name`), which is deprecated and fails with "Database
> instance … does not exist". The exact `database` resource-path id (`.../databases/
> <id>`) is confirmed at validate time via
> `databricks postgres list-databases projects/capstone-pg/branches/production`.

> **The exact resource sub-shapes are authoritatively validated by
> `databricks bundle validate -t dev`.** The app-resource git-source shape is:
> `git_repository: { provider, url }` (both required; provider case-insensitive, e.g.
> `gitHub`) + `git_source: { branch, source_code_path }`, and
> **do NOT also set app-level `source_code_path`** (DABs rejects "both git_source and
> source_code_path are set"). The implementation plan MUST run `bundle validate` and
> fix the config against its error messages before any deploy — the schema, not this
> spec, is the source of truth for exact keys.

## Deploy sequence (dev)

1. **Build + commit dist on t5:** un-ignore `capstone-app/app/frontend/dist/` (scoped so
   it stays ignored elsewhere), `cd capstone-app/app/frontend && bun run build`, commit
   `dist/` + `app.yaml` + bundle files on `t5`, push.
2. `databricks bundle validate -t dev --profile fevm-test-jg` — fix config against
   errors until clean.
3. `databricks bundle deploy -t dev --profile fevm-test-jg`.
4. **[user/manual]** Enable **OBO user-authorization preview** (Workspace admin →
   Settings → Apps → User authorization) — without it, OBO scopes are silently dropped
   and metrics/dashboard/Genie 401 on the deployed app.
5. Get the app SP id: `databricks apps get customer360-dev --profile fevm-test-jg`
   (`service_principal_id` / `service_principal_client_id`).
6. **[user: PAT]** Register the SP-bound GitHub credential so the source pull works:
   `databricks git-credentials create --json '{"git_provider":"gitHub", ...,
   "principal_id": <APP_SP_ID>}'` (public repo → may be skippable; try the run first).
7. `databricks bundle run customer360 -t dev --profile fevm-test-jg` — pulls the `t5`
   commit and starts the app.
8. **[user/manual]** Allowlist the app domain for **embed** (Workspace Settings →
   Security → External Access → Embed Dashboard) — only affects a future iframe embed;
   the native T4 dashboard doesn't need it, but the "Open in workspace" deep-links do
   not either. Optional for this dev deploy.
9. First app load per user → **consent screen** for the OBO scopes (click Authorize once).

## Verify (Done when)

- `databricks bundle validate -t dev` passes.
- Deployed app's source shows **git repository + branch** in the workspace UI (not a
  folder upload).
- `bundle run` pulls the matching commit SHA (Deployments tab).
- App reaches RUNNING (`databricks apps get customer360-dev` → app_status RUNNING).
- App URL loads the cockpit; list/detail/notes work; after OBO consent, metrics +
  dashboard + Genie work live.

## Explicitly NOT doing

- No `resources/jobs.yml` (T7) / `resources/lakebase.yml` (T1) in the bundle yet.
- No prod deploy (dev target only); `prod` target is declared but not run.
- No secret-scope `valueFrom` wiring.
- No source-upload fallback (git-source is required by T8).

## Risks / flagged

- **dist committed** on t5 — accepted as the only git-source-compatible option; scoped
  to the deploy branch to minimize ugliness.
- **Node-at-runtime avoided** — build is local, not at cold-start.
- If the SP git-credential/PAT step is needed and unavailable, the deploy stops at
  step 7 with a source-pull 401 — surfaced to the user, not worked around.
- Exact DABs app-resource git-source key nesting is validated at build time, not
  assumed from this spec.
