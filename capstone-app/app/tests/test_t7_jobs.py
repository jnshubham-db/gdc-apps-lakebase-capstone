"""T7 forward-ETL job endpoint tests via FastAPI TestClient.

The Jobs SDK calls are stubbed by overriding get_sp_client, so these run
without Databricks auth (no `live` marker needed).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.deps import get_sp_client
from backend.main import app


def test_run_models_importable():
    from backend.models import RunStatus, RunSummary, RunTrigger

    t = RunTrigger(run_id=42)
    assert t.run_id == 42
    s = RunStatus(
        run_id=42,
        state="RUNNING",
        result_state=None,
        start_time=None,
        duration_ms=None,
        run_page_url=None,
    )
    assert s.state == "RUNNING"
    assert (
        RunSummary(
            run_id=1, state="TERMINATED", result_state="SUCCESS", start_time=1, duration_ms=2
        ).result_state
        == "SUCCESS"
    )


def test_settings_has_forward_etl_job_id():
    assert "forward_etl_job_id" in Settings.model_fields


@pytest.fixture
def stub_sp():
    """A WorkspaceClient stub whose .jobs records calls and returns canned runs."""
    calls = {}

    def run_now(job_id):
        calls["run_now"] = job_id
        return SimpleNamespace(run_id=777)

    def get_run(run_id):
        calls["get_run"] = run_id
        return SimpleNamespace(
            run_id=run_id,
            state=SimpleNamespace(
                life_cycle_state=SimpleNamespace(value="RUNNING"),
                result_state=None,
            ),
            start_time=1000,
            run_duration=None,
            run_page_url="https://example/run",
        )

    def list_runs(job_id, limit):
        calls["list_runs"] = (job_id, limit)
        return [
            SimpleNamespace(
                run_id=1,
                state=SimpleNamespace(
                    life_cycle_state=SimpleNamespace(value="TERMINATED"),
                    result_state=SimpleNamespace(value="SUCCESS"),
                ),
                start_time=500,
                run_duration=1234,
            )
        ]

    sp = SimpleNamespace(
        jobs=SimpleNamespace(run_now=run_now, get_run=get_run, list_runs=list_runs)
    )
    sp._calls = calls
    return sp


@pytest.fixture
def client_with_job(stub_sp):
    from backend.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "forward_etl_job_id", "12345")
    app.dependency_overrides[get_sp_client] = lambda: stub_sp
    with TestClient(app) as c:
        yield c, stub_sp
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_jobs_routes_registered():
    paths = set(app.openapi()["paths"].keys())
    assert "/api/jobs/run-forward-etl" in paths
    assert "/api/jobs/runs/{run_id}" in paths
    assert "/api/jobs/runs" in paths


def test_trigger_calls_run_now_with_job_id(client_with_job):
    c, sp = client_with_job
    r = c.post("/api/jobs/run-forward-etl")
    assert r.status_code == 200, r.text
    assert r.json() == {"run_id": 777}
    assert sp._calls["run_now"] == 12345


def test_get_run_maps_state(client_with_job):
    c, _ = client_with_job
    r = c.get("/api/jobs/runs/777")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == 777
    assert body["state"] == "RUNNING"
    assert body["run_page_url"] == "https://example/run"


def test_list_runs_maps_summary(client_with_job):
    c, sp = client_with_job
    r = c.get("/api/jobs/runs")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows[0]["result_state"] == "SUCCESS"
    assert rows[0]["duration_ms"] == 1234
    assert sp._calls["list_runs"] == (12345, 10)


def test_endpoints_503_without_job_configured():
    from backend.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    object.__setattr__(s, "forward_etl_job_id", None)
    app.dependency_overrides[get_sp_client] = lambda: SimpleNamespace(jobs=None)
    with TestClient(app) as c:
        assert c.post("/api/jobs/run-forward-etl").status_code == 503
        assert c.get("/api/jobs/runs").status_code == 503
    app.dependency_overrides.clear()
    get_settings.cache_clear()
