from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

METRICS = {
    "request_rate_per_s": {
        "min_delta": 0.5,
        "query": 'sum(rate(http_requests_total{job="__SVC__"}[1m]))'
    },
    "error_ratio": {
        "min_delta": 0.05,
        "query": '(sum(rate(http_requests_total{job="__SVC__",status=~"5.."}[1m])) or vector(0))'
                 ' / sum(rate(http_requests_total{job="__SVC__"}[1m]))'
    },
    "latency_p95_seconds": {
        "min_delta": 0.1,
        "query": 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="__SVC__"}[1m])))'
    },
}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def summarize_series(
    values: List[Tuple[Any, Any]],
    min_delta: float = 0.0,
    jump_factor: float = 2.0
) -> Optional[Dict[str, Any]]:
    pts: List[Tuple[float, float]] = []
    for ts, raw in values:
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(v) or math.isinf(v):
            continue
        pts.append((float(ts), v))

    if not pts:
        return None

    nums = [v for _, v in pts]
    n_base = max(1, len(pts) // 4)
    baseline = sum(nums[:n_base]) / n_base
    peak_ts, peak = max(pts, key=lambda p: p[1])
    jump_at = next(
        (iso(ts) for ts, v in pts[n_base:]
         if v - baseline > min_delta and v > baseline * jump_factor),
        None
    )

    return {
        "baseline": round(baseline, 4),
        "min": round(min(nums), 4),
        "max": round(peak, 4),
        "avg": round(sum(nums) / len(nums), 4),
        "last": round(nums[-1], 4),
        "peak_at": iso(peak_ts),
        "jump_at": jump_at,
        "points": len(pts),
    }
