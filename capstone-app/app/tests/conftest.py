"""Shared fixtures for the app tests.

The ``live`` marker gates tests that need a real Databricks identity (the
``fevm-test-jg`` CLI profile) and a reachable Lakebase endpoint. They *skip*
rather than fail when auth can't be resolved, so the suite stays green in a
credential-less CI while still running end-to-end on a developer laptop.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _databricks_auth_available() -> bool:
    """True if a WorkspaceClient can authenticate (profile creds present)."""
    try:
        from backend.auth import sp_client

        sp_client().current_user.me()
        return True
    except Exception:  # noqa: BLE001 — any auth/network failure means "skip live"
        return False


def pytest_collection_modifyitems(config, items):
    """Skip ``live`` tests when Databricks auth isn't available."""
    if _databricks_auth_available():
        return
    skip = pytest.mark.skip(reason="no Databricks auth (fevm-test-jg profile / Lakebase)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def make_request(headers: dict[str, str]):
    """A minimal stand-in for a request object: only ``.headers`` is read."""
    return SimpleNamespace(headers=headers)
