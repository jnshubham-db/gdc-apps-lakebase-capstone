"""T3 endpoint tests via FastAPI TestClient.

Auth deps are overridden so a specific actor identity is injected without a
real request; the DB/warehouse work is live, so these carry the ``live``
marker and skip without Databricks auth.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_actor_email, get_obo_client
from backend.main import app

pytestmark = pytest.mark.live

_ACTOR = "test-rep@acme.com"


@pytest.fixture
def client():
    from backend.auth import sp_client

    app.dependency_overrides[get_actor_email] = lambda: _ACTOR
    app.dependency_overrides[get_obo_client] = sp_client  # warehouse as SP for the test
    with TestClient(app) as c:  # triggers lifespan (index) + shutdown (pool close)
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def a_customer_id(client) -> str:
    return client.get("/api/customers", params={"page_size": 1}).json()["items"][0]["customer_id"]


# --- list -------------------------------------------------------------------


def test_list_shape_and_cap(client):
    r = client.get("/api/customers", params={"page": 1, "page_size": 5})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert len(body["items"]) <= 5
    assert body["total"] > len(body["items"])


def test_page_size_over_cap_is_422(client):
    assert client.get("/api/customers", params={"page_size": 101}).status_code == 422


def test_filter_narrows_results(client):
    all_n = client.get("/api/customers", params={"page_size": 1}).json()["total"]
    filtered = client.get("/api/customers", params={"page_size": 1, "min_ltv": 100000}).json()
    assert filtered["total"] <= all_n


# --- detail -----------------------------------------------------------------


def test_detail_ok(client, a_customer_id):
    r = client.get(f"/api/customers/{a_customer_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["customer_id"] == a_customer_id
    assert len(body["transactions"]) <= 20


def test_detail_unknown_404(client):
    assert client.get("/api/customers/NOPE-0000").status_code == 404


# --- metrics ----------------------------------------------------------------


def test_metrics_ok(client, a_customer_id):
    r = client.get(f"/api/customers/{a_customer_id}/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == a_customer_id
    assert body["lifetime_spend"] >= 0
    assert isinstance(body["top_categories"], list)


# --- writes -----------------------------------------------------------------


def test_add_note_writes_audit(client, a_customer_id):
    r = client.post(f"/api/customers/{a_customer_id}/notes", json={"note_text": "hello from test"})
    assert r.status_code == 201
    note_id = r.json()["note_id"]

    # audit row exists for this note
    import asyncio

    from backend.db import lakebase_sp

    async def _count():
        async with lakebase_sp() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM customer_audit_log "
                "WHERE action='add_note' AND payload->>'note_id' = %s",
                (note_id,),
            )
            return (await cur.fetchone())[0]

    assert asyncio.run(_count()) == 1


def test_segment_override_idempotent(client, a_customer_id):
    payload = {"override_segment": "S1", "reason": "test idempotency"}
    first = client.post(f"/api/customers/{a_customer_id}/segment", json=payload)
    second = client.post(f"/api/customers/{a_customer_id}/segment", json=payload)
    assert first.status_code == 200 and second.status_code == 200

    import asyncio

    from backend.db import lakebase_sp

    async def _count():
        async with lakebase_sp() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM customer_segment_overrides_staging WHERE customer_id = %s",
                (a_customer_id,),
            )
            return (await cur.fetchone())[0]

    assert asyncio.run(_count()) == 1
