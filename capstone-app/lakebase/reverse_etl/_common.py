"""Shared helpers for the T1 reverse-ETL scripts.

Loads config from ``app/.env`` and provides a psycopg (v3) connection to
Lakebase authenticated with a short-lived OAuth token minted via the
Databricks CLI profile. These scripts are run by a human operator (the
project owner) from their laptop — the app itself connects as its service
principal (see ``app/backend/db.py``, T2), not through this module.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient
from dotenv import dotenv_values

# repo layout: lakebase/reverse_etl/_common.py  ->  app/.env
_ENV_PATH = Path(__file__).resolve().parents[2] / "app" / ".env"


def load_env() -> dict[str, str]:
    """Return the capstone config from ``app/.env`` (never mutates os.environ)."""
    if not _ENV_PATH.exists():
        raise FileNotFoundError(f"Expected capstone config at {_ENV_PATH}")
    cfg = {k: v for k, v in dotenv_values(_ENV_PATH).items() if v is not None}
    required = ["DATABRICKS_PROFILE", "PGHOST", "PGDATABASE"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise KeyError(f"Missing keys in {_ENV_PATH}: {', '.join(missing)}")
    return cfg


def workspace_client(cfg: dict[str, str]) -> WorkspaceClient:
    return WorkspaceClient(profile=cfg["DATABRICKS_PROFILE"])


def connect(cfg: dict[str, str], w: WorkspaceClient) -> psycopg.Connection:
    """Open a psycopg connection to Lakebase as the current CLI user.

    The password is a fresh OAuth token (valid ~1h) — fine for these one-shot
    admin scripts. ``sslmode=require`` is mandatory for Lakebase.
    """
    token = w.config.oauth_token().access_token
    user = w.current_user.me().user_name
    return psycopg.connect(
        host=cfg["PGHOST"],
        port=int(os.getenv("PGPORT", "5432")),
        dbname=cfg["PGDATABASE"],
        user=user,
        password=token,
        sslmode="require",
        connect_timeout=30,
    )
