from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.adapters.container_status import get_container_status
from app.collect import collect_logs, collect_metrics
from app.config import load_deploys, load_services_config, settings
from app.graph import ServiceGraph, evaluate_service_health, find_candidates
from app.timeline import build_timeline
from app.timeutil import compute_window, seconds_to_iso

app = FastAPI(title="Incident Investigator", version="0.1.0")


class InvestigationRequest(BaseModel):
    service: str
    window_minutes: Optional[int] = Field(default=None, ge=1)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/services")
def list_services() -> Dict[str, Any]:
    return load_services_config()


@app.post("/investigations")
def create_investigation(req: InvestigationRequest) -> Dict[str, Any]:
    services = load_services_config()
    if req.service not in services:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{req.service}' not found in services catalog",
        )

    svc_cfg = services[req.service]
    depends_on: List[str] = svc_cfg.get("depends_on", [])

    win_mins = req.window_minutes if req.window_minutes is not None else settings.default_window_minutes
    if win_mins > settings.max_window_minutes:
        win_mins = settings.max_window_minutes

    start_sec, end_sec = compute_window(win_mins)

    # 1. Collect telemetry across catalog services
    all_metrics: Dict[str, Dict[str, Any]] = {}
    all_logs: Dict[str, Dict[str, Any]] = {}
    container_statuses: Dict[str, Dict[str, Any]] = {}

    for s_name, s_info in services.items():
        all_metrics[s_name] = collect_metrics(s_name, start_sec, end_sec)
        all_logs[s_name] = collect_logs(s_name, start_sec, end_sec)
        container_name = s_info.get("container", s_name) if isinstance(s_info, dict) else s_name
        container_statuses[s_name] = get_container_status(container_name)

    # 2. Build graph & evaluate health
    graph = ServiceGraph(services)
    for s_name in services:
        is_healthy, reasons = evaluate_service_health(
            all_metrics[s_name],
            container_statuses.get(s_name),
        )
        graph.mark_health(s_name, is_healthy, {"reasons": reasons})

    # 3. Pre-rank candidates
    candidates = find_candidates(graph, container_statuses)

    # 4. Build timeline
    deploys = load_deploys()
    timeline = build_timeline(
        all_metrics,
        all_logs,
        container_statuses,
        deploys,
        start_sec,
        end_sec,
    )

    return {
        "service": req.service,
        "depends_on": depends_on,
        "window": {
            "start": seconds_to_iso(start_sec),
            "end": seconds_to_iso(end_sec),
            "minutes": win_mins,
        },
        "metrics": all_metrics[req.service],
        "logs": all_logs[req.service],
        "graph": graph.to_dict(),
        "candidates": candidates,
        "timeline": timeline,
    }
