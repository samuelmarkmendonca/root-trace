from typing import Any, Dict, List, Optional
from app.timeutil import seconds_to_iso, to_epoch_seconds


def build_timeline(
    metrics_by_service: Dict[str, Dict[str, Any]],
    logs_by_service: Dict[str, Dict[str, Any]],
    container_statuses: Dict[str, Dict[str, Any]],
    deploys: Optional[List[Dict[str, Any]]] = None,
    start_sec: Optional[float] = None,
    end_sec: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Merges metric jump times, log pattern first-seen times, container restarts/OOMKills,
    and deploys.json events into one sorted list.
    """
    events: List[Dict[str, Any]] = []

    # 1. Deploys
    if deploys:
        for d in deploys:
            raw_time = d.get("time") or d.get("timestamp")
            if raw_time is None:
                continue
            try:
                t_sec = to_epoch_seconds(raw_time)
            except Exception:
                continue

            if start_sec is not None and end_sec is not None:
                # Include deploys slightly before the window (within 10m) or inside window
                if t_sec < (start_sec - 600) or t_sec > (end_sec + 60):
                    continue

            svc = d.get("service", "unknown")
            version = d.get("version", "")
            change = d.get("change", "")
            if version and change:
                desc = f"Deploy {version}: {change}"
            elif version:
                desc = f"Deploy {version}"
            elif change:
                desc = f"Deploy: {change}"
            else:
                desc = f"Deployment of {svc}"

            events.append({
                "timestamp": seconds_to_iso(t_sec),
                "epoch": t_sec,
                "type": "deploy",
                "service": svc,
                "description": desc,
                "details": d,
            })

    # 2. Metric Jump Times
    for svc, metrics in metrics_by_service.items():
        if not isinstance(metrics, dict):
            continue
        for m_name, m_data in metrics.items():
            if not isinstance(m_data, dict):
                continue
            jump_at = m_data.get("jump_at")
            if not jump_at:
                continue
            try:
                j_sec = to_epoch_seconds(jump_at)
            except Exception:
                continue

            if start_sec is not None and end_sec is not None:
                if j_sec < start_sec or j_sec > end_sec:
                    continue

            max_val = m_data.get("max", m_data.get("last", "spike"))
            base_val = m_data.get("baseline", "0")
            events.append({
                "timestamp": seconds_to_iso(j_sec),
                "epoch": j_sec,
                "type": "metric_jump",
                "service": svc,
                "description": f"Metric {m_name} jumped to {max_val} (baseline {base_val})",
                "details": {
                    "metric": m_name,
                    "baseline": base_val,
                    "max": max_val,
                    "peak_at": m_data.get("peak_at"),
                },
            })

    # 3. Log pattern first-seen times
    for svc, logs in logs_by_service.items():
        if not isinstance(logs, dict):
            continue
        patterns = logs.get("patterns", [])
        if not isinstance(patterns, list):
            continue
        for p in patterns:
            if not isinstance(p, dict):
                continue
            first_seen = p.get("first_seen")
            if not first_seen:
                continue
            try:
                fs_sec = to_epoch_seconds(first_seen)
            except Exception:
                continue

            if start_sec is not None and end_sec is not None:
                if fs_sec < start_sec or fs_sec > end_sec:
                    continue

            pat_str = p.get("pattern", "error")
            cnt = p.get("count", 1)
            events.append({
                "timestamp": seconds_to_iso(fs_sec),
                "epoch": fs_sec,
                "type": "log_pattern",
                "service": svc,
                "description": f"First seen error pattern: '{pat_str}' (seen {cnt} times)",
                "details": p,
            })

    # 4. Container restarts, OOMKills, and down events
    for svc, cs in container_statuses.items():
        if not isinstance(cs, dict):
            continue

        if cs.get("oom_killed"):
            fin_ts = cs.get("finished_at")
            if fin_ts:
                try:
                    fin_sec = to_epoch_seconds(fin_ts)
                    if start_sec is None or (start_sec <= fin_sec <= (end_sec or fin_sec)):
                        events.append({
                            "timestamp": seconds_to_iso(fin_sec),
                            "epoch": fin_sec,
                            "type": "container_oom",
                            "service": svc,
                            "description": f"Container {svc} killed by OOM (exit code {cs.get('exit_code', 137)})",
                            "details": cs,
                        })
                except Exception:
                    pass

        if cs.get("restart_count", 0) > 0:
            st_ts = cs.get("started_at")
            if st_ts:
                try:
                    st_sec = to_epoch_seconds(st_ts)
                    if start_sec is None or (start_sec <= st_sec <= (end_sec or st_sec)):
                        events.append({
                            "timestamp": seconds_to_iso(st_sec),
                            "epoch": st_sec,
                            "type": "container_restart",
                            "service": svc,
                            "description": f"Container {svc} restarted (restart count: {cs.get('restart_count')})",
                            "details": cs,
                        })
                except Exception:
                    pass

        if not cs.get("running", True) or cs.get("status") in ("exited", "dead", "stopped"):
            fin_ts = cs.get("finished_at")
            if fin_ts:
                try:
                    fin_sec = to_epoch_seconds(fin_ts)
                    if start_sec is None or (start_sec <= fin_sec <= (end_sec or fin_sec)):
                        events.append({
                            "timestamp": seconds_to_iso(fin_sec),
                            "epoch": fin_sec,
                            "type": "container_down",
                            "service": svc,
                            "description": f"Container {svc} stopped (status: {cs.get('status')}, exit code: {cs.get('exit_code', 0)})",
                            "details": cs,
                        })
                except Exception:
                    pass

    # Sort chronologically
    events.sort(key=lambda e: e["epoch"])
    return events
