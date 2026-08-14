"""Shared helpers for the T9 Lakebase-ops scripts.

Wraps the ``databricks postgres`` CLI (branch lifecycle, endpoint host/token)
and opens psycopg connections to an arbitrary branch endpoint. Run by a human
operator (project owner) from a laptop — never by the deployed app.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import psycopg
from dotenv import dotenv_values

# repo layout: capstone-app/lakebase/ops/_common.py -> capstone-app/app/.env
_ENV_PATH = Path(__file__).resolve().parents[2] / "app" / ".env"


def load_cfg() -> dict[str, str]:
    if not _ENV_PATH.exists():
        raise FileNotFoundError(f"Expected capstone config at {_ENV_PATH}")
    cfg = {k: v for k, v in dotenv_values(_ENV_PATH).items() if v is not None}
    missing = [k for k in ("DATABRICKS_PROFILE", "PGDATABASE") if not cfg.get(k)]
    if missing:
        raise KeyError(f"Missing keys in {_ENV_PATH}: {', '.join(missing)}")
    return cfg


def cli_json(*args: str, profile: str):
    """Run ``databricks <args> -o json --profile <profile>`` and parse stdout."""
    cmd = ["databricks", *args, "-o", "json", "--profile", profile]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def current_user(profile: str) -> str:
    return cli_json("current-user", "me", profile=profile)["userName"]


def create_branch(
    profile: str,
    project: str,
    branch_id: str,
    *,
    source_branch: str | None = None,
    source_branch_time: str | None = None,
    ttl: str = "14400s",
    replace: bool = True,
) -> str:
    """Create a branch; return its resource path. PITR via source_branch_time (RFC3339)."""
    spec: dict[str, object] = {"ttl": ttl}
    if source_branch:
        spec["source_branch"] = source_branch
    if source_branch_time:
        spec["source_branch_time"] = source_branch_time
    args = [
        "postgres",
        "create-branch",
        f"projects/{project}",
        branch_id,
        "--json",
        json.dumps({"spec": spec}),
    ]
    if replace:
        args.append("--replace-existing")
    cli_json(*args, profile=profile)
    return f"projects/{project}/branches/{branch_id}"


def delete_branch(profile: str, branch_path: str) -> None:
    subprocess.run(
        ["databricks", "postgres", "delete-branch", branch_path, "--profile", profile],
        capture_output=True,
        text=True,
        check=True,
    )


def readwrite_endpoint(profile: str, branch_path: str) -> str:
    data = cli_json("postgres", "list-endpoints", branch_path, profile=profile)
    endpoints = data if isinstance(data, list) else data.get("endpoints", [])
    if not endpoints:
        raise RuntimeError(f"No endpoints on {branch_path}")
    return endpoints[0]["name"]


def endpoint_host(profile: str, endpoint_path: str) -> str:
    return cli_json("postgres", "get-endpoint", endpoint_path, profile=profile)[
        "status"
    ]["hosts"]["host"]


def endpoint_token(profile: str, endpoint_path: str) -> str:
    return cli_json(
        "postgres", "generate-database-credential", endpoint_path, profile=profile
    )["token"]


def connect(host: str, user: str, dbname: str, token: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=int(os.getenv("PGPORT", "5432")),
        dbname=dbname,
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )


def percentiles(samples_ms: list[float], pcts=(50, 95, 99)) -> dict[int, float]:
    """Nearest-rank percentiles over the sample list (ms)."""
    if not samples_ms:
        raise ValueError("no samples")
    ordered = sorted(samples_ms)
    out: dict[int, float] = {}
    for p in pcts:
        rank = max(1, math.ceil(p / 100 * len(ordered)))
        out[p] = ordered[rank - 1]
    return out
