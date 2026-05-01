#!/usr/bin/env python3
"""
Capstone installer — Databricks Apps + Lakebase.

Single-file, pure-Python installer designed to be invoked via:

    curl -fsSL https://raw.githubusercontent.com/jnshubham/gdc-apps-lakebase-capstone/main/install.py | python3

It will:
  1. Install its own deps (databricks-sdk, click) via pip --user.
  2. Prompt for: Databricks CLI profile, catalog, schema, warehouse, Lakebase
     instance settings, dashboard / Genie titles, parent workspace path.
  3. Download this repo as a tarball, extract to a temp dir.
  4. Upload notebooks 01 / 02 / 04 / 05 to the workspace, submit them as
     ephemeral one-shot jobs, capture their dbutils.notebook.exit() JSON.
  5. Copy the blank scaffold into a directory you choose, write app/.env with
     all the captured IDs, and print a final summary.

Notebook 03 (synced + staging tables) is intentionally *not* run — it is a
reference for capstone tasks T2–T5.
"""

from __future__ import annotations

# ── Bootstrap (stdlib only) ───────────────────────────────────────────────────
import os
import shutil
import subprocess
import sys

REPO_OWNER = "jnshubham"
REPO_NAME = "gdc-apps-lakebase-capstone"
REPO_BRANCH = "main"
REPO_TARBALL_URL = (
    f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{REPO_BRANCH}.tar.gz"
)

_BOOTSTRAP_MARKER = "_CAPSTONE_INSTALLER_BOOTSTRAPPED"


def _ensure_deps() -> None:
    """Install databricks-sdk + click into --user site if missing, then re-exec."""
    if os.environ.get(_BOOTSTRAP_MARKER) == "1":
        return
    missing = []
    try:
        import databricks.sdk  # noqa: F401
    except ImportError:
        missing.append("databricks-sdk")
    try:
        import click  # noqa: F401
    except ImportError:
        missing.append("click")
    if missing:
        print(f"[bootstrap] installing {', '.join(missing)} (one-time, --user)…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", *missing]
        )
    if shutil.which("databricks") is None:
        print(
            "\nERROR: Databricks CLI not found on PATH.\n"
            "Install it: https://docs.databricks.com/en/dev-tools/cli/install.html\n"
            "Then re-run this installer.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ[_BOOTSTRAP_MARKER] = "1"
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *sys.argv[1:]])


_ensure_deps()


# ── Real imports (after bootstrap) ────────────────────────────────────────────
import io
import json
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

import click
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError
from databricks.sdk.service.jobs import NotebookTask, SubmitTask
from databricks.sdk.service.workspace import ImportFormat, Language


# ── UI helpers ────────────────────────────────────────────────────────────────
BOX = "─" * 72


def banner(text: str) -> None:
    click.echo()
    click.echo(BOX)
    click.echo(click.style(f" {text}", bold=True))
    click.echo(BOX)


def step(num: int, text: str) -> None:
    click.echo(click.style(f"\n[{num}] {text}", fg="cyan", bold=True))


def info(text: str) -> None:
    click.echo(f"    {text}")


def ok(text: str) -> None:
    click.echo(click.style(f"    ✓ {text}", fg="green"))


def fail(text: str) -> None:
    click.echo(click.style(f"    ✗ {text}", fg="red"), err=True)


# ── Step 2: profile + connection check ───────────────────────────────────────
def connect() -> tuple[WorkspaceClient, str, str]:
    profile = click.prompt(
        "Databricks CLI profile",
        default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
    )
    try:
        w = WorkspaceClient(profile=profile)
        me = w.current_user.me()
    except Exception as e:
        fail(f"Could not connect with profile '{profile}': {e}")
        click.echo(
            f"\nFix: run `databricks auth login --profile {profile}` first, then rerun."
        )
        sys.exit(1)
    host = w.config.host or ""
    user = me.user_name or "unknown"
    ok(f"Connected as {user}  ({host})")
    return w, profile, host


# ── Step 3: parameter prompts ─────────────────────────────────────────────────
def pick_warehouse(w: WorkspaceClient) -> tuple[str, str]:
    """Show a numbered list of warehouses; return (id, name)."""
    whs = list(w.warehouses.list())
    if not whs:
        fail("No SQL warehouses visible. Create one first.")
        sys.exit(1)
    info("Available SQL warehouses:")
    for i, wh in enumerate(whs):
        state = wh.state.value if wh.state else "?"
        wtype = (wh.warehouse_type.value if wh.warehouse_type else "").replace(
            "WAREHOUSE_TYPE_UNSPECIFIED", ""
        )
        click.echo(f"      [{i}] {wh.name:<40} state={state:<10} id={wh.id}")
    while True:
        choice = click.prompt(
            "Pick a warehouse (number or full ID)", default="0"
        ).strip()
        if choice.isdigit() and 0 <= int(choice) < len(whs):
            wh = whs[int(choice)]
            return wh.id, wh.name
        for wh in whs:
            if wh.id == choice:
                return wh.id, wh.name
        fail(f"'{choice}' is not a valid index or warehouse ID. Try again.")


def collect_params(w: WorkspaceClient) -> dict:
    step(3, "Collect parameters")
    catalog = click.prompt("Catalog name", default="capstone")
    schema = click.prompt("Schema name (in catalog)", default="gold")
    wh_id, wh_name = pick_warehouse(w)
    info(f"Selected: {wh_name} ({wh_id})")
    instance_name = click.prompt("Lakebase instance name", default="capstone-pg")
    capacity = click.prompt("Lakebase capacity", default="CU_1")
    pg_uc_catalog = click.prompt(
        "Lakebase UC catalog (registered in UC)", default="capstone_lakebase"
    )
    db_name = click.prompt("Postgres database name", default="capstone_db")
    dashboard_name = click.prompt(
        "Dashboard display name", default="Customer 360 — Capstone"
    )
    space_title = click.prompt(
        "Genie space title", default="Customer 360 — Capstone Genie"
    )
    parent_path = click.prompt(
        "Workspace folder for notebooks/dashboard",
        default="/Workspace/Shared/capstone",
    )
    return {
        "catalog": catalog,
        "schema": schema,
        "warehouse_id": wh_id,
        "warehouse_name": wh_name,
        "instance_name": instance_name,
        "capacity": capacity,
        "uc_catalog_name": pg_uc_catalog,
        "database_name": db_name,
        "dashboard_name": dashboard_name,
        "space_title": space_title,
        "parent_path": parent_path,
    }


def confirm_params(p: dict) -> None:
    banner("Confirm")
    longest = max(len(k) for k in p)
    for k, v in p.items():
        click.echo(f"  {k:<{longest}}  {v}")
    if not click.confirm("\nProceed with these settings?", default=True):
        click.echo("Aborted.")
        sys.exit(0)


# ── Step 4: download repo bundle ──────────────────────────────────────────────
def download_bundle() -> Path:
    step(4, "Download installer bundle (notebooks + scaffold)")
    info(f"GET {REPO_TARBALL_URL}")
    tmp = Path(tempfile.mkdtemp(prefix="capstone-"))
    tar_path = tmp / "repo.tar.gz"
    with urllib.request.urlopen(REPO_TARBALL_URL) as resp, tar_path.open("wb") as f:
        shutil.copyfileobj(resp, f)
    with tarfile.open(tar_path) as tf:
        tf.extractall(tmp)
    extracted = next(d for d in tmp.iterdir() if d.is_dir() and d.name != "__pycache__")
    ok(f"Extracted to {extracted}")
    return extracted


# ── Step 5: run notebooks as ephemeral jobs ──────────────────────────────────
NOTEBOOKS_TO_RUN = [
    {
        "file": "01_generate_gold_data.py",
        "name": "01_generate_gold_data",
        "params": lambda p: {"catalog": p["catalog"], "schema": p["schema"]},
        "label": "Generate gold-layer Delta tables",
    },
    {
        "file": "02_create_lakebase_instance.py",
        "name": "02_create_lakebase_instance",
        "params": lambda p: {
            "instance_name": p["instance_name"],
            "uc_catalog_name": p["uc_catalog_name"],
            "capacity": p["capacity"],
            "database_name": p["database_name"],
        },
        "label": "Provision Lakebase instance (1–3 min)",
    },
    {
        "file": "04_create_aibi_dashboard.py",
        "name": "04_create_aibi_dashboard",
        "params": lambda p: {
            "catalog": p["catalog"],
            "schema": p["schema"],
            "warehouse_id": p["warehouse_id"],
            "dashboard_name": p["dashboard_name"],
            "parent_path": p["parent_path"],
        },
        "label": "Create AI/BI dashboard",
    },
    {
        "file": "05_create_genie_space.py",
        "name": "05_create_genie_space",
        "params": lambda p: {
            "catalog": p["catalog"],
            "schema": p["schema"],
            "warehouse_id": p["warehouse_id"],
            "space_title": p["space_title"],
            "parent_path": p["parent_path"],
        },
        "label": "Create Genie space",
    },
]


def upload_notebook(w: WorkspaceClient, local_path: Path, ws_path: str) -> None:
    """Upload a notebook source file to the workspace path (overwrite=True)."""
    w.workspace.mkdirs(os.path.dirname(ws_path))
    content = local_path.read_bytes()
    w.workspace.upload(
        path=ws_path,
        content=io.BytesIO(content),
        format=ImportFormat.SOURCE,
        language=Language.PYTHON,
        overwrite=True,
    )


def run_notebook_job(
    w: WorkspaceClient,
    host: str,
    notebook_ws_path: str,
    base_parameters: dict,
    label: str,
) -> dict:
    """Submit a one-shot job, wait, return the parsed exit JSON."""
    run_name = f"capstone-installer-{Path(notebook_ws_path).name}"
    info(f"Submitting job: {run_name}")
    submitted = w.jobs.submit(
        run_name=run_name,
        tasks=[
            SubmitTask(
                task_key="run",
                notebook_task=NotebookTask(
                    notebook_path=notebook_ws_path,
                    base_parameters=base_parameters,
                ),
            )
        ],
    )
    run_id = submitted.run_id
    info(f"Run URL: {host}/jobs/runs/{run_id}")
    info(f"Waiting for: {label}")
    last_state = None
    while True:
        run = w.jobs.get_run(run_id=run_id)
        state = run.state.life_cycle_state.value if run.state and run.state.life_cycle_state else "?"
        if state != last_state:
            click.echo(f"      … {state}")
            last_state = state
        if run.state and run.state.life_cycle_state and run.state.life_cycle_state.value in (
            "TERMINATED",
            "SKIPPED",
            "INTERNAL_ERROR",
        ):
            break
        time.sleep(8)
    result_state = (
        run.state.result_state.value if run.state and run.state.result_state else "?"
    )
    if result_state != "SUCCESS":
        fail(f"Run failed: {result_state}. See {host}/jobs/runs/{run_id}")
        msg = run.state.state_message if run.state else ""
        if msg:
            click.echo(f"      message: {msg}", err=True)
        sys.exit(1)
    if not run.tasks:
        fail("Run has no tasks — cannot fetch output.")
        sys.exit(1)
    task_run_id = run.tasks[0].run_id
    output = w.jobs.get_run_output(run_id=task_run_id)
    nb_out = output.notebook_output.result if output.notebook_output else None
    if not nb_out:
        fail("Notebook produced no exit value.")
        sys.exit(1)
    try:
        parsed = json.loads(nb_out)
    except json.JSONDecodeError as e:
        fail(f"Could not parse notebook exit JSON: {e}")
        click.echo(f"      raw: {nb_out[:200]}", err=True)
        sys.exit(1)
    ok(f"Done. Captured {len(parsed)} value(s): {', '.join(parsed.keys())}")
    return parsed


def run_all_notebooks(
    w: WorkspaceClient, host: str, extracted: Path, params: dict
) -> dict:
    step(5, "Run setup notebooks (01, 02, 04, 05)")
    parent = params["parent_path"]
    state: dict = {}
    for nb in NOTEBOOKS_TO_RUN:
        local = extracted / "capstone" / "notebooks" / nb["file"]
        if not local.exists():
            fail(f"Missing notebook in bundle: {local}")
            sys.exit(1)
        ws_path = f"{parent}/{nb['name']}"
        click.echo()
        click.echo(click.style(f"  ▸ {nb['file']}", fg="yellow", bold=True))
        upload_notebook(w, local, ws_path)
        captured = run_notebook_job(w, host, ws_path, nb["params"](params), nb["label"])
        state.update(captured)
    return state


# ── Step 6: drop scaffold + write .env ───────────────────────────────────────
def drop_scaffold(extracted: Path, params: dict, state: dict, profile: str, host: str) -> Path:
    step(6, "Drop scaffold into your local working directory")
    while True:
        dest = click.prompt(
            "Where should the scaffold be created?", default="./capstone-app"
        )
        dest_path = Path(dest).expanduser().resolve()
        if dest_path.exists() and any(dest_path.iterdir()):
            if click.confirm(
                f"  '{dest_path}' is not empty. Overwrite contents anyway?",
                default=False,
            ):
                shutil.rmtree(dest_path)
                break
            continue
        break
    src = extracted / "capstone-scaffold"
    shutil.copytree(src, dest_path)
    # also copy the notebooks (they're useful as reference + they hold notebook 03)
    shutil.copytree(extracted / "capstone", dest_path / "capstone", dirs_exist_ok=True)
    ok(f"Scaffold dropped at {dest_path}")
    env_path = dest_path / "app" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_lines = [
        f"# Generated by capstone installer on {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"DATABRICKS_HOST={host}",
        f"DATABRICKS_PROFILE={profile}",
        f"CAPSTONE_CATALOG={state.get('CAPSTONE_CATALOG', params['catalog'])}",
        f"CAPSTONE_SCHEMA={state.get('CAPSTONE_SCHEMA', params['schema'])}",
        f"WAREHOUSE_ID={state.get('WAREHOUSE_ID', params['warehouse_id'])}",
        f"DASHBOARD_ID={state.get('DASHBOARD_ID', '')}",
        f"GENIE_SPACE_ID={state.get('GENIE_SPACE_ID', '')}",
        f"PGHOST={state.get('PGHOST', '')}",
        f"PGDATABASE={state.get('PGDATABASE', '')}",
        f"PG_INSTANCE_NAME={state.get('PG_INSTANCE_NAME', '')}",
        f"PG_UC_CATALOG={state.get('PG_UC_CATALOG', '')}",
        f"SECRET_SCOPE={state.get('SECRET_SCOPE', '')}",
        f"PARENT_PATH={params['parent_path']}",
    ]
    env_path.write_text("\n".join(env_lines) + "\n")
    ok(f"Wrote {env_path}")
    return dest_path


# ── Step 7: final summary ────────────────────────────────────────────────────
def summary(host: str, dest: Path, state: dict) -> None:
    banner("All set")
    dash_id = state.get("DASHBOARD_ID", "")
    genie_id = state.get("GENIE_SPACE_ID", "")
    if dash_id:
        click.echo(f"  Dashboard:  {host}/dashboardsv3/{dash_id}/published")
    if genie_id:
        click.echo(f"  Genie:      {host}/genie/rooms/{genie_id}")
    if state.get("PGHOST"):
        click.echo(f"  Lakebase:   {state['PGHOST']}/{state.get('PGDATABASE', '')}")
        click.echo(f"  Instance:   {state.get('PG_INSTANCE_NAME', '')}")
        click.echo(f"  Secret scope: {state.get('SECRET_SCOPE', '')}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  cd {dest}")
    click.echo("  cat CAPSTONE_TASKS.md            # your task list")
    click.echo("  cat capstone/notebooks/03_create_synced_and_staging.py   # T2-T5 reference")
    click.echo()
    click.echo("Reminder: notebook 03 (synced + staging tables) is *your* task — see T2-T5.")


# ── Main ──────────────────────────────────────────────────────────────────────
@click.command()
def main() -> None:
    banner("Capstone installer — Databricks Apps + Lakebase")
    click.echo(f"  Repo: https://github.com/{REPO_OWNER}/{REPO_NAME}")
    click.echo("  This will: provision data, Lakebase, dashboard, Genie — then drop a scaffold here.")
    click.echo("  Notebook 03 (synced + staging tables) is intentionally left for you to do.")
    step(1, "Bootstrap")
    ok("databricks-sdk + click present")
    step(2, "Connect to Databricks workspace")
    w, profile, host = connect()
    params = collect_params(w)
    confirm_params(params)
    extracted = download_bundle()
    try:
        state = run_all_notebooks(w, host, extracted, params)
        state["WAREHOUSE_ID"] = state.get("WAREHOUSE_ID", params["warehouse_id"])
        dest = drop_scaffold(extracted, params, state, profile, host)
        summary(host, dest, state)
    finally:
        # Best-effort cleanup of the temp extraction dir's parent.
        parent_tmp = extracted.parent
        try:
            shutil.rmtree(parent_tmp)
        except Exception:
            pass


if __name__ == "__main__":
    main()
