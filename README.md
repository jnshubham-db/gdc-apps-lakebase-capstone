# Capstone — Databricks Apps + Lakebase

A hands-on capstone project: build "Customer 360 for Acme Retail" — a
React + FastAPI app on Databricks Apps, backed by Lakebase (synced reads
and writable staging tables), embedded AI/BI dashboards, Genie chat, and a
scheduled forward-ETL job.

The kit ships a one-line installer, a blank scaffold (you write the code),
and a checklist of 14 tasks (`CAPSTONE_TASKS.md`) covering every skill from
the Apps + Lakebase training: OBO/SP auth, Lakebase CRUD, synced + staging
tables, reverse + forward ETL, Genie integration, dashboard embed, DABs
CI/CD, and external M2M/U2M auth.

## Install

Run this in a clean directory on your laptop:

```bash
curl -fsSL https://raw.githubusercontent.com/jnshubham/gdc-apps-lakebase-capstone/main/install.sh | bash
```

The installer is interactive — it will prompt for a Databricks CLI profile,
catalog name, warehouse, Lakebase config, etc. Total time: ~10–15 min.

**The installer installs nothing on your machine.** It uses only what you
already have: `bash`, `curl`, `tar`, `python3` (stdlib only — for JSON
parsing), and the `databricks` CLI. All Python / SDK work happens server-side
in your Databricks workspace.

### Prerequisites

- [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/install.html) (≥ 0.230) authed with at least one profile (`databricks auth login --profile <name>`)
- `python3` on `PATH` (preinstalled on macOS / Linux)
- A **Serverless SQL Warehouse** in the workspace (the installer lets you pick from a list)
- Workspace permissions: create catalogs, create database instances (Lakebase), create dashboards / Genie spaces, run jobs

## What the installer does

| Step | Provisions | How |
|---|---|---|
| 1 | Gold Delta tables (`customers`, `transactions`, `products`, `support_tickets`, `customer_segments`) | runs `01_generate_gold_data.py` as an ephemeral job |
| 2 | Lakebase (managed Postgres) instance + UC registration + secret scope | runs `02_create_lakebase_instance.py` |
| 3 | Lakeview AI/BI dashboard (5 widgets, anomalies highlighted) | runs `04_create_aibi_dashboard.py` |
| 4 | Genie space scoped to the 5 gold tables | runs `05_create_genie_space.py` |
| 5 | Drops the **blank scaffold** into a directory you choose | local `cp -r` + writes `app/.env` |

**Notebook 03** (synced + staging tables) is intentionally **not** run — it is
the reference for capstone tasks T2–T5, which you complete yourself.

## What you build

Everything else. Every file under `app/`, `resources/`, `lakebase/`,
`examples/`, and `tests/` is a 0-byte stub. Open
[`capstone-scaffold/CAPSTONE_TASKS.md`](./capstone-scaffold/CAPSTONE_TASKS.md)
and work through tasks T1–T14 — that document is the source of truth.

## Layout

```
gdc-apps-lakebase-capstone/
├── install.py                    one-shot installer (curl target)
├── README.md                     you are here
├── capstone/notebooks/           5 setup notebooks (installer runs 4; you run 03)
└── capstone-scaffold/            dropped into your working dir on install
    ├── CAPSTONE_TASKS.md         14-task checklist — your spec
    ├── README.md                 scaffold-side quickstart
    ├── databricks.yml            DABs root (empty stub)
    ├── resources/                DABs resources (empty stubs)
    ├── app/
    │   ├── backend/              FastAPI (empty stubs)
    │   └── frontend/             React + Vite (empty stubs)
    ├── lakebase/                 reverse-ETL spec + forward-ETL patterns A/B
    ├── examples/                 M2M / U2M curl scripts
    └── tests/smoke_test.py
```

## Troubleshooting

- **"No SQL warehouses visible"** — your profile lacks workspace access; double-check with `databricks current-user me --profile <name>`.
- **Notebook 02 hangs** — Lakebase provisioning takes 1–3 min; the installer polls every 8s. If it times out >5 min, check the `Run URL` printed.
- **Notebook 04 dashboard shows "No data"** — re-run only notebook 04 (the installer does this automatically) and verify the warehouse you picked is *running*.
