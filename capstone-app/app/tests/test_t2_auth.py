"""T2 integration tests — auth clients and the Lakebase connection helper.

Two kinds:

* **Live** (``@pytest.mark.live``) — exercise the real workspace/Lakebase:
  the SP identity, ``SELECT 1`` through the pool, and pool reuse. These map
  directly to the T2 "Done when" checks. Skipped without Databricks auth.
* **Pure** — the OBO header seam (``obo_client`` / ``actor_email``), which the
  live tests can't cover locally because no ``X-Forwarded-*`` headers exist
  off-platform.
"""

from __future__ import annotations

import pytest

from backend.auth import actor_email, obo_client, sp_client
from backend.db import close_pool, lakebase_sp

from .conftest import make_request

# --- pure: OBO / actor seam (no network) ------------------------------------


def test_obo_client_reads_forwarded_token():
    client = obo_client(make_request({"X-Forwarded-Access-Token": "tok-123"}))
    assert client.config.token == "tok-123"


def test_obo_client_raises_without_header():
    with pytest.raises(PermissionError, match="X-Forwarded-Access-Token"):
        obo_client(make_request({}))


def test_actor_email_prefers_forwarded_header():
    assert actor_email(make_request({"X-Forwarded-Email": "rep@acme.com"})) == "rep@acme.com"


# --- live: real workspace + Lakebase ----------------------------------------


@pytest.mark.live
def test_sp_client_has_identity():
    """done-when: sp_client() authenticates and resolves an identity."""
    assert sp_client().current_user.me().user_name


@pytest.mark.live
def test_lakebase_sp_select_one():
    """done-when: SELECT 1 via lakebase_sp() returns 1."""
    try:
        with lakebase_sp() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        close_pool()


@pytest.mark.live
def test_lakebase_sp_pool_reuse():
    """Two sequential checkouts both work (token minted per physical conn)."""
    try:
        for _ in range(2):
            with lakebase_sp() as conn, conn.cursor() as cur:
                cur.execute("SELECT 42")
                assert cur.fetchone() == (42,)
    finally:
        close_pool()
