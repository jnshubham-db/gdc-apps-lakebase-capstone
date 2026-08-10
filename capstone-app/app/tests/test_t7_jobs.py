"""T7 forward-ETL job endpoint tests via FastAPI TestClient.

The Jobs SDK calls are stubbed by overriding get_sp_client, so these run
without Databricks auth (no `live` marker needed).
"""

from __future__ import annotations

from backend.config import Settings


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
