from typing import Any, Dict, List
import httpx
from app.config import settings


class PrometheusError(Exception):
    pass


def query_range(query: str, start: float, end: float, step: str = "15s") -> List[Dict[str, Any]]:
    try:
        r = httpx.get(
            f"{settings.prometheus_url}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=10.0,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise PrometheusError(f"Prometheus request failed: {type(e).__name__}: {e}") from e

    body = r.json()
    if body.get("status") != "success":
        raise PrometheusError(f"Prometheus error: {body.get('error', 'unknown')}")

    data = body.get("data", {})
    return data.get("result", [])
