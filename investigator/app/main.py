from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.collect import collect_logs, collect_metrics
from app.config import load_services_config, settings
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
            detail=f"Service '{req.service}' not found in services catalog"
        )

    svc_cfg = services[req.service]
    depends_on: List[str] = svc_cfg.get("depends_on", [])

    win_mins = req.window_minutes if req.window_minutes is not None else settings.default_window_minutes
    if win_mins > settings.max_window_minutes:
        win_mins = settings.max_window_minutes

    start_sec, end_sec = compute_window(win_mins)

    metrics = collect_metrics(req.service, start_sec, end_sec)
    logs = collect_logs(req.service, start_sec, end_sec)

    return {
        "service": req.service,
        "depends_on": depends_on,
        "window": {
            "start": seconds_to_iso(start_sec),
            "end": seconds_to_iso(end_sec),
            "minutes": win_mins,
        },
        "metrics": metrics,
        "logs": logs,
    }
