from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from crewinsight.azure_clients import AzureSearchRAG
from crewinsight.config import settings
from crewinsight.crew.process import CrewCoordinator
from crewinsight.crew.tools import FormatterTool, ResearchToolset
from crewinsight.data_sources.finnhub import FinnhubClient
from crewinsight.models.report import CrewReport, CrewRunRequest, CrewRunStatus
from crewinsight.rate_limit import AzureTableStore, TableRateLimiter
from crewinsight.telemetry import CrewMetrics

router = APIRouter(prefix="/api/v1")

runs: Dict[str, Dict[str, Any]] = {}
metrics = CrewMetrics()

_finnhub = FinnhubClient(api_key=settings.finnhub_api_key) if settings.finnhub_api_key else None
coordinator = CrewCoordinator(
    ResearchToolset(
        AzureSearchRAG(
            endpoint=settings.azure_search_endpoint,
            api_key=settings.azure_search_api_key,
            index_name=settings.azure_search_index,
        ),
        finnhub_client=_finnhub,
    ),
    FormatterTool(),
    metrics=metrics,
)

_store = AzureTableStore(
    account_name=settings.azure_storage_account_name,
    account_key=settings.azure_storage_account_key,
)
rate_limiter = TableRateLimiter(
    store=_store,
    per_ip_limit=settings.rate_limit_per_ip_count,
    global_daily_limit=settings.rate_limit_global_daily,
)


async def _execute_run(run_id: str, company: str, segment: str) -> None:
    runs[run_id]["status"] = CrewRunStatus.running

    def on_agent_start(role: str) -> None:
        runs[run_id]["active_agent"] = role

    try:
        report = await coordinator.run(run_id, company, segment, on_agent_start=on_agent_start)
        runs[run_id]["status"] = CrewRunStatus.complete
        runs[run_id]["active_agent"] = None
        runs[run_id]["report"] = report
    except Exception as exc:
        runs[run_id]["status"] = CrewRunStatus.failed
        runs[run_id]["active_agent"] = None
        runs[run_id]["error"] = str(exc)


@router.post("/research")
async def launch_research(request: Request, body: CrewRunRequest, background_tasks: BackgroundTasks) -> Dict[str, str]:
    await rate_limiter.check_ip(request)
    await rate_limiter.check_global()
    run_id = str(uuid4())
    runs[run_id] = {
        "status": CrewRunStatus.pending,
        "company": body.company,
        "segment": body.segment,
    }
    background_tasks.add_task(_execute_run, run_id, body.company, body.segment)
    return {"run_id": run_id, "status": CrewRunStatus.pending}


@router.get("/status/{run_id}")
async def status(run_id: str) -> Dict[str, Any]:
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {
        "run_id": run_id,
        "status": run["status"],
        "active_agent": run.get("active_agent"),
        "error": run.get("error"),
    }


@router.get("/report/{run_id}")
async def report(run_id: str) -> CrewReport:
    run = runs.get(run_id)
    if not run or run.get("status") != CrewRunStatus.complete:
        raise HTTPException(status_code=404, detail="report not available")
    return run["report"]


@router.get("/metrics")
async def metrics_endpoint() -> Dict[str, Any]:
    daily_count = await _store.get_count(f"global:{_current_date_utc()}")
    return {
        **metrics.aggregate(),
        "daily_requests": daily_count if daily_count is not None else "unavailable",
        "daily_limit": settings.rate_limit_global_daily,
    }


def _current_date_utc() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
