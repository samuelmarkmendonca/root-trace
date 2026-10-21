from typing import Any, Dict, List, Tuple
import httpx
from app.config import settings
from app.logutil import summarize_log_entries
from app.timeutil import to_epoch_nanoseconds, TimestampInput


class LokiError(Exception):
    pass


def get_error_logs(
    service: str,
    start: TimestampInput,
    end: TimestampInput,
    limit: int = 500,
    max_patterns: int = 10,
) -> Dict[str, Any]:
    start_ns = to_epoch_nanoseconds(start)
    end_ns = to_epoch_nanoseconds(end)

    query = f'{{service="{service}"}} |~ "ERROR|CRITICAL"'
    params = {
        "query": query,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": limit,
    }

    try:
        r = httpx.get(
            f"{settings.loki_url}/loki/api/v1/query_range",
            params=params,
            timeout=10.0,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LokiError(f"Loki request failed: {type(e).__name__}: {e}") from e

    body = r.json()
    if body.get("status") != "success":
        raise LokiError(f"Loki error: {body.get('error', 'unknown')}")

    results = body.get("data", {}).get("result", [])
    entries: List[Tuple[str, str]] = []
    for stream in results:
        values = stream.get("values", [])
        for val in values:
            if len(val) >= 2:
                entries.append((val[0], val[1]))

    # Sort entries by timestamp
    entries.sort(key=lambda x: int(x[0]) if x[0].isdigit() else x[0])

    res = summarize_log_entries(entries, max_patterns=max_patterns)
    res["source"] = "loki"
    return res
