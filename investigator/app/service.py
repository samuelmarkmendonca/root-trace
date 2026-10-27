import logging
import time
from typing import Any, Dict, List
from app.adapters.container_status import get_container_status
from app.agent.loop import InvestigatorAgent
from app.agent.schema import AgentStepEvent
from app.collect import collect_logs, collect_metrics
from app.config import load_deploys, load_services_config, settings
from app.graph import ServiceGraph, evaluate_service_health, find_candidates
from app.store import InvestigationStore, store as global_store
from app.timeline import build_timeline
from app.timeutil import compute_window, seconds_to_iso

logger = logging.getLogger("investigator.service")


def collect_investigation_evidence(
    service: str,
    window_minutes: int,
) -> Dict[str, Any]:
    services = load_services_config()
    win_mins = window_minutes if window_minutes <= settings.max_window_minutes else settings.max_window_minutes
    start_sec, end_sec = compute_window(win_mins)

    all_metrics: Dict[str, Dict[str, Any]] = {}
    all_logs: Dict[str, Dict[str, Any]] = {}
    container_statuses: Dict[str, Dict[str, Any]] = {}

    for s_name, s_info in services.items():
        all_metrics[s_name] = collect_metrics(s_name, start_sec, end_sec)
        all_logs[s_name] = collect_logs(s_name, start_sec, end_sec)
        container_name = s_info.get("container", s_name) if isinstance(s_info, dict) else s_name
        container_statuses[s_name] = get_container_status(container_name)

    graph = ServiceGraph(services)
    for s_name in services:
        is_healthy, reasons = evaluate_service_health(
            all_metrics[s_name],
            container_statuses.get(s_name),
        )
        graph.mark_health(s_name, is_healthy, {"reasons": reasons})

    candidates = find_candidates(graph, container_statuses)
    deploys = load_deploys()
    timeline = build_timeline(
        all_metrics,
        all_logs,
        container_statuses,
        deploys,
        start_sec,
        end_sec,
    )

    svc_cfg = services.get(service, {})
    depends_on = svc_cfg.get("depends_on", []) if isinstance(svc_cfg, dict) else []

    return {
        "service": service,
        "depends_on": depends_on,
        "window": {
            "start": seconds_to_iso(start_sec),
            "end": seconds_to_iso(end_sec),
            "minutes": win_mins,
        },
        "metrics": all_metrics.get(service, {}),
        "logs": all_logs.get(service, {}),
        "graph": graph.to_dict(),
        "candidates": candidates,
        "timeline": timeline,
        "all_metrics": all_metrics,
        "all_logs": all_logs,
        "container_statuses": container_statuses,
    }


def execute_investigation(
    inv_id: str,
    service: str,
    window_minutes: int,
    investigation_store: InvestigationStore = global_store,
) -> None:
    logger.info(f"Starting investigation {inv_id} for service {service} (window: {window_minutes}m)")
    try:
        investigation_store.add_event(
            inv_id,
            AgentStepEvent(
                step=0,
                type="thought",
                content=f"Starting telemetry collection across architecture for '{service}'...",
                timestamp=time.time(),
            ),
        )

        evidence = collect_investigation_evidence(service, window_minutes)
        investigation_store.set_evidence(inv_id, evidence)

        candidate_names = [c["service"] if isinstance(c, dict) else str(c) for c in evidence.get("candidates", [])]
        candidate_str = ", ".join(candidate_names) or "None"
        investigation_store.add_event(
            inv_id,
            AgentStepEvent(
                step=0,
                type="thought",
                content=f"Telemetry correlated. Pre-ranked root cause candidates: [{candidate_str}]. Invoking LLM diagnostic agent...",
                timestamp=time.time(),
            ),
        )

        agent = InvestigatorAgent()
        report, _ = agent.run(
            evidence,
            on_event=lambda ev: investigation_store.add_event(inv_id, ev),
        )

        investigation_store.complete(inv_id, report.model_dump())
        logger.info(f"Investigation {inv_id} completed successfully")

    except Exception as e:
        logger.exception(f"Investigation {inv_id} failed: {e}")
        investigation_store.fail(inv_id, f"Investigation execution error: {type(e).__name__}: {str(e)}")
