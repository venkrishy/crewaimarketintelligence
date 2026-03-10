from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

from crewinsight.azure_clients import AzureSearchRAG
from crewinsight.config import settings
from crewinsight.crew.process import CrewCoordinator
from crewinsight.crew.tools import FormatterTool, ResearchToolset
from crewinsight.models.report import CrewReport, CrewRunRequest, CrewRunStatus
from crewinsight.telemetry import CrewMetrics

router = APIRouter(prefix="/api/v1")

runs: Dict[str, Dict[str, Any]] = {}
metrics = CrewMetrics()
coordinator = CrewCoordinator(
    ResearchToolset(
        AzureSearchRAG(
            endpoint=settings.azure_search_endpoint,
            api_key=settings.azure_search_api_key,
            index_name=settings.azure_search_index,
        )
    ),
    FormatterTool(),
    metrics=metrics,
)

async def _execute_run(run_id: str, company: str, segment: str) -> None:
    runs[run_id]["status"] = CrewRunStatus.running
    try:
        report = await coordinator.run(run_id, company, segment)
        runs[run_id]["status"] = CrewRunStatus.complete
        runs[run_id]["report"] = report
    except Exception as exc:
        runs[run_id]["status"] = CrewRunStatus.failed
        runs[run_id]["error"] = str(exc)


@router.post("/research")
async def launch_research(request: CrewRunRequest, background_tasks: BackgroundTasks) -> Dict[str, str]:
    run_id = str(uuid4())
    runs[run_id] = {
        "status": CrewRunStatus.pending,
        "company": request.company,
        "segment": request.segment,
    }
    background_tasks.add_task(_execute_run, run_id, request.company, request.segment)
    return {"run_id": run_id, "status": CrewRunStatus.pending}


@router.get("/status/{run_id}")
async def status(run_id: str) -> Dict[str, Any]:
    run = runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {
        "run_id": run_id,
        "status": run["status"],
        "active_agent": "unknown",
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
    return metrics.aggregate()
