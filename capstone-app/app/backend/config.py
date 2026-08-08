"""App-runtime configuration.

The app runs in two environments:

  * **Deployed** on Databricks Apps — the runtime injects real env vars
    (``PGHOST``, ``LAKEBASE_ENDPOINT``, the service-principal OAuth creds
    ``DATABRICKS_CLIENT_ID`` / ``DATABRICKS_CLIENT_SECRET``, …).
  * **Local dev** — none of that is injected; config comes from ``app/.env``
    and the client authenticates via ``DATABRICKS_PROFILE``.

``load_env()`` merges the two so callers don't care which they're in: values
from ``app/.env`` are the base, and the vars the deployed runtime injects
(``PG*``, ``LAKEBASE_ENDPOINT``, the SP creds) override them when present. A
dev-machine artifact like an ambient ``DATABRICKS_PROFILE`` must *not* win, so
the override is a narrow allowlist rather than "any env var".
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

# app/backend/config.py -> app/.env
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Vars the Databricks Apps runtime injects; these override app/.env at deploy.
_RUNTIME_KEYS = {
    "LAKEBASE_ENDPOINT",
    "DATABRICKS_HOST",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
}


def _is_runtime_key(k: str) -> bool:
    return k.startswith("PG") or k in _RUNTIME_KEYS


def load_env() -> dict[str, str]:
    """Return ``app/.env`` with runtime-injected vars overlaid on top."""
    base = {k: v for k, v in dotenv_values(_ENV_PATH).items() if v is not None}
    base.update({k: v for k, v in os.environ.items() if _is_runtime_key(k)})
    return base


def deployed() -> bool:
    """True when running on Databricks Apps (SP creds are injected)."""
    return "DATABRICKS_CLIENT_ID" in os.environ
