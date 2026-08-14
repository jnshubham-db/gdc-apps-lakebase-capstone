"""T5 Genie endpoint tests via FastAPI TestClient.

The conversation test is live (real Genie space via OBO, overridden to the SP
client in the fixture) and skips without Databricks auth. A non-live test
asserts the routes are registered.
"""

from __future__ import annotations

import time

import pytest
from backend.deps import get_obo_client
from backend.main import app
from fastapi.testclient import TestClient

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


@pytest.fixture
def client():
    from backend.auth import sp_client

    app.dependency_overrides[get_obo_client] = sp_client  # Genie as SP for the test
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_genie_routes_registered(client):
    paths = set(app.openapi()["paths"].keys())
    assert "/api/genie/conversations" in paths
    assert "/api/genie/conversations/{cid}/messages" in paths
    assert "/api/genie/conversations/{cid}/messages/{mid}" in paths


@pytest.mark.live
def test_conversation_answers_with_text(client):
    start = client.post(
        "/api/genie/conversations",
        json={"content": "Which segment has the highest average lifetime value?"},
    )
    assert start.status_code == 200, start.text
    cid = start.json()["conversation_id"]
    mid = start.json()["message_id"]

    deadline = time.time() + 60
    status = None
    while time.time() < deadline:
        r = client.get(f"/api/genie/conversations/{cid}/messages/{mid}")
        assert r.status_code == 200, r.text
        status = r.json()["status"]
        if status in _TERMINAL:
            break
        time.sleep(2)

    assert status == "COMPLETED", f"terminal status was {status}"
    body = r.json()
    assert body["text"] and len(body["text"]) > 0
