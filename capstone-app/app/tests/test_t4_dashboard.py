"""T4 endpoint tests via FastAPI TestClient.

Config is static (no auth); analytics hits the warehouse via OBO, overridden
to the SP client for the test, so those carry the ``live`` marker.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_obo_client
from backend.main import app


@pytest.fixture
def client():
    from backend.auth import sp_client

    app.dependency_overrides[get_obo_client] = sp_client  # warehouse as SP for the test
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_config_shape(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"databricks_host", "dashboard_id", "genie_space_id"}
    assert body["databricks_host"].startswith("http")
