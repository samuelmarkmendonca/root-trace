import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.adapters.container_status import get_container_status
from app.collect import collect_logs, collect_metrics
from app.config import load_services_config, settings
from app.service import execute_investigation
from app.store import store

logger = logging.getLogger("investigator.api")

app = FastAPI(title="Incident Investigator", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


STATIC_DIR = Path(__file__).resolve().parent / "static"


class InvestigationRequest(BaseModel):
    service: str
    window_minutes: Optional[int] = Field(default=None, ge=1)
    sync: Optional[bool] = False


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/info")
def get_info() -> Dict[str, Any]:
    services = load_services_config()
    return {
        "active_model": settings.llm_model,
        "llm_url": settings.llm_url,
        "services": list(services.keys()),
        "max_window_minutes": settings.max_window_minutes,
        "default_window_minutes": settings.default_window_minutes,
    }


@app.get("/services")
def list_services() -> Dict[str, Any]:
    return load_services_config()


@app.post("/investigations")
def create_investigation(
    req: InvestigationRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    services = load_services_config()
    if req.service not in services:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{req.service}' not found in services catalog",
        )

    win_mins = req.window_minutes if req.window_minutes is not None else settings.default_window_minutes
    if win_mins > settings.max_window_minutes:
        win_mins = settings.max_window_minutes

    inv_id = f"inv_{uuid.uuid4().hex[:8]}"
    store.create(inv_id, req.service, win_mins)

    if req.sync:
        # Run synchronously (useful for tests or programmatic blocking calls)
        execute_investigation(inv_id, req.service, win_mins, store)
        record = store.get(inv_id) or {}
        evidence = record.get("evidence") or {}
        report = record.get("report") or {}
        root_causes = report.get("root_causes", []) if isinstance(report, dict) else []
        return {
            "id": inv_id,
            "service": req.service,
            "status": record.get("status", "completed"),
            "report": report,
            "ranked_causes": root_causes,
            "graph": evidence.get("graph", {}),
            "candidates": evidence.get("candidates", []),
            "timeline": evidence.get("timeline", []),
            "metrics": evidence.get("metrics", {}),
            "all_metrics": evidence.get("all_metrics", {}),
            "logs": evidence.get("logs", {}),
            "all_logs": evidence.get("all_logs", {}),
            "events": record.get("events", []),
        }

    # Asynchronous background execution (Stage 11 lifecycle)
    background_tasks.add_task(execute_investigation, inv_id, req.service, win_mins, store)

    return {
        "id": inv_id,
        "status": "running",
        "service": req.service,
        "window_minutes": win_mins,
    }


@app.get("/investigations")
def list_investigations() -> List[Dict[str, Any]]:
    return store.list_all()


@app.get("/investigations/{inv_id}")
def get_investigation(inv_id: str) -> Dict[str, Any]:
    record = store.get(inv_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Investigation '{inv_id}' not found")

    evidence = record.get("evidence") or {}
    report = record.get("report") or {}
    root_causes = report.get("root_causes", []) if isinstance(report, dict) else []
    return {
        "id": record.get("id"),
        "service": record.get("service"),
        "window_minutes": record.get("window_minutes"),
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "report": report,
        "ranked_causes": root_causes,
        "graph": evidence.get("graph"),
        "candidates": evidence.get("candidates"),
        "timeline": evidence.get("timeline"),
        "metrics": evidence.get("metrics"),
        "all_metrics": evidence.get("all_metrics", {}),
        "logs": evidence.get("logs"),
        "all_logs": evidence.get("all_logs", {}),
        "events": record.get("events", []),
        "error": record.get("error"),
    }


@app.get("/investigations/{inv_id}/stream")
async def stream_investigation(inv_id: str):
    record = store.get(inv_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Investigation '{inv_id}' not found")

    return EventSourceResponse(store.stream_events(inv_id))


# Fault Injection Simulator API (for UI)
def _post_fault(service: str, path: str) -> bool:
    import httpx
    # Candidate URLs for container and host
    port_map = {"db": ("http://db:8000", "http://localhost:8003", "http://host.docker.internal:8003"),
                "checkout": ("http://checkout:8000", "http://localhost:8002", "http://host.docker.internal:8002")}
    urls = port_map.get(service, [])
    for base in urls:
        try:
            r = httpx.post(f"{base}{path}", timeout=3.0)
            if r.status_code < 500:
                return True
        except Exception:
            continue
    return False


@app.post("/api/faults/{fault_id}")
def trigger_fault(fault_id: str) -> Dict[str, Any]:
    import json
    import time
    from app.config import load_deploys, settings

    if fault_id == "db_latency":
        ok = _post_fault("db", "/fault/latency?ms=800")
        return {"status": "ok" if ok else "warning", "message": "Injected db_latency (800ms)"}

    elif fault_id == "db_errors":
        ok = _post_fault("db", "/fault/errors?rate=0.6")
        return {"status": "ok" if ok else "warning", "message": "Injected db_errors (rate=0.6)"}

    elif fault_id == "db_pool_exhausted":
        ok = _post_fault("db", "/fault/pool?hold_seconds=60")
        return {"status": "ok" if ok else "warning", "message": "Injected db_pool_exhausted (60s hold)"}

    elif fault_id == "checkout_memory_leak":
        ok = _post_fault("checkout", "/fault/leak?mb_per_request=1")
        return {"status": "ok" if ok else "warning", "message": "Injected checkout_memory_leak (1MB/req)"}

    elif fault_id == "bad_deploy":
        ok = _post_fault("checkout", "/fault/errors?rate=0.4")
        # Append deploy event to deploys.json
        try:
            deploys_path = Path(settings.deploys_file)
            if not deploys_path.is_absolute():
                candidates = [
                    deploys_path,
                    Path(__file__).resolve().parent.parent / deploys_path,
                    Path(__file__).resolve().parent.parent.parent / deploys_path,
                    Path("/data/deploys.json"),
                ]
                for c in candidates:
                    if c.parent.exists():
                        deploys_path = c
                        break
            
            existing = []
            if deploys_path.exists():
                try:
                    with open(deploys_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            
            existing.append({
                "time": int(time.time()),
                "service": "checkout",
                "version": "v2",
                "change": "payment_timeout_ms 2000 -> 50",
            })
            with open(deploys_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not record deploy event: {e}")

        return {"status": "ok" if ok else "warning", "message": "Injected bad_deploy (v2 deploy event + 5xx error rate)"}

    elif fault_id == "reset":
        _post_fault("db", "/fault/reset")
        _post_fault("checkout", "/fault/reset")
        return {"status": "ok", "message": "All faults reset to healthy"}

    raise HTTPException(status_code=400, detail=f"Unknown fault '{fault_id}'")


# Mount static assets & UI
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_ui():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return {"message": "Incident Investigator UI loading..."}
