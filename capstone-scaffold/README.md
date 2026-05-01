# Customer 360 — Lakebase + Apps Capstone (scaffold)

A starter kit. The scaffold gives you the wiring — DABs config, FastAPI +
React skeleton, ETL stubs, GitHub Actions. **You write the logic.**

## What you'll build

> A "customer success" web app for Acme Retail. Reps browse customers, see a
> 360° view, leave notes / override segments (writes to a Lakebase staging
> table), ask Genie ad-hoc questions, view an embedded AI/BI dashboard, and
> trigger a forward-ETL job. A separate `/api/external/*` surface exposes the
> same data to partners over M2M/U2M auth.

The full task list is in **[CAPSTONE_TASKS.md](./CAPSTONE_TASKS.md)** — that
is your source of truth.

## Layout

```
capstone-scaffold/
├── databricks.yml             DABs root
├── resources/                 DABs resource defs (app, jobs, lakebase)
├── app/
│   ├── app.yaml               Apps runtime config
│   ├── backend/               FastAPI — TODO stubs in routers/*
│   └── frontend/              React + Vite — TODO stubs in pages/*
├── lakebase/
│   ├── reverse_etl/           synced-table notes + declarative spec
│   └── forward_etl/           pattern A (psycopg) and B (Lakeflow) — pick one
├── examples/                  curl examples for M2M + U2M
└── tests/smoke_test.py        post-deploy sanity check
```

## Quickstart

The repo's `curl ... | python3` installer (see the **repo root README**) has
already provisioned: gold tables, Lakebase instance, AI/BI dashboard, Genie
space — and dropped this scaffold into your chosen directory with `app/.env`
populated.

What's left for you (full list in `CAPSTONE_TASKS.md`):

```bash
# 1. Synced + staging tables — the installer skipped notebook 03 on purpose;
#    it's tasks T2-T5 of your capstone. See:
#    capstone/notebooks/03_create_synced_and_staging.py  (reference)

# 2. Local dev loop (after you fill in pyproject.toml + package.json):
cd app
uv sync
cd frontend && npm install && npm run build
cd ..
uv run uvicorn backend.main:app --reload --port 8000

# 3. First deploy:
cd ..
databricks bundle validate --target dev
databricks bundle deploy   --target dev
databricks bundle run customer360
```

## Submission

You're done when **every task in `CAPSTONE_TASKS.md` is checked** *and* the
smoke test passes against your deployed app:

```bash
APP_URL=https://your-app... DATABRICKS_TOKEN=... python tests/smoke_test.py
```
