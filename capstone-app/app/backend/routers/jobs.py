"""Forward-ETL job endpoints (T7).

Three thin wrappers over the Jobs API, run as the app SP (background work, not
user-attributed). The app never runs the drain itself — it triggers the
serverless notebook job declared in the bundle (resources/jobs.yml) and polls
its run status. The job id is bundle-injected via FORWARD_ETL_JOB_ID.
"""

from __future__ import annotations

import asyncio

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..deps import Sp
from ..models import RunStatus, RunSummary, RunTrigger

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_id() -> str:
    job_id = get_settings().forward_etl_job_id
    if not job_id:
        raise HTTPException(status_code=503, detail="forward-ETL job not configured")
    return job_id


def _state(run) -> tuple[str, str | None]:
    """(life_cycle_state, result_state) as plain strings."""
    st = run.state
    life = getattr(st.life_cycle_state, "value", None) or str(st.life_cycle_state)
    result = getattr(st.result_state, "value", None) if st and st.result_state else None
    return life, result


def _trigger(w: WorkspaceClient, job_id: str) -> RunTrigger:
    run = w.jobs.run_now(job_id)
    return RunTrigger(run_id=run.run_id)


def _get_run(w: WorkspaceClient, run_id: int) -> RunStatus:
    run = w.jobs.get_run(run_id)
    life, result = _state(run)
    return RunStatus(
        run_id=run.run_id,
        state=life,
        result_state=result,
        start_time=run.start_time,
        duration_ms=getattr(run, "run_duration", None),
        run_page_url=getattr(run, "run_page_url", None),
    )


def _list_runs(w: WorkspaceClient, job_id: str) -> list[RunSummary]:
    runs = w.jobs.list_runs(job_id=job_id, limit=10)
    out: list[RunSummary] = []
    for run in runs:
        life, result = _state(run)
        out.append(
            RunSummary(
                run_id=run.run_id,
                state=life,
                result_state=result,
                start_time=run.start_time,
                duration_ms=getattr(run, "run_duration", None),
            )
        )
    return out


@router.post("/run-forward-etl", response_model=RunTrigger)
async def run_forward_etl(sp: Sp) -> RunTrigger:
    return await asyncio.to_thread(_trigger, sp, _job_id())


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: int, sp: Sp) -> RunStatus:
    _job_id()  # 503 if not configured
    return await asyncio.to_thread(_get_run, sp, run_id)


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(sp: Sp) -> list[RunSummary]:
    return await asyncio.to_thread(_list_runs, sp, _job_id())
