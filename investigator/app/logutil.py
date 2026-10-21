from collections import OrderedDict
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple, Union

# Docker-SDK path lines have a leading timestamp token; Loki path lines do not. Make it optional.
LINE_RE = re.compile(r"^(?:(?P<ts>\d{4}-\S+)\s+)?(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<msg>.*)$")
BAD = {"ERROR", "CRITICAL"}


def pattern(msg: str) -> str:
    return re.sub(r"\d+", "N", msg)[:200]  # '142 timeouts' ~ '97 timeouts'


def summarize_log_text(text: str, max_patterns: int = 10) -> Dict[str, Any]:
    scanned = 0
    errors = 0
    groups: Dict[str, Dict[str, Any]] = OrderedDict()
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        scanned += 1
        if m["level"] not in BAD:
            continue
        errors += 1
        key, ts = pattern(m["msg"]), (m["ts"] or "")[:19]
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "count": 1,
                "pattern": key,
                "example": m["msg"][:200],
                "first_seen": ts,
                "last_seen": ts,
            }
        else:
            g["count"] += 1
            g["last_seen"] = ts or g["last_seen"]
    top = sorted(groups.values(), key=lambda g: g["count"], reverse=True)[:max_patterns]
    return {"lines_scanned": scanned, "error_lines": errors, "patterns": top}


def summarize_log_entries(
    entries: List[Tuple[Union[int, str], str]],
    max_patterns: int = 10,
) -> Dict[str, Any]:
    """
    Summarize log entries where each entry is (ts_ns, line).
    ts_ns is nanoseconds timestamp (from Loki) or ISO timestamp.
    """
    scanned = 0
    errors = 0
    groups: Dict[str, Dict[str, Any]] = OrderedDict()

    # Sort entries chronologically if needed
    def parse_ts(ts_val: Union[int, str]) -> str:
        if isinstance(ts_val, (int, float)) or (isinstance(ts_val, str) and ts_val.isdigit()):
            sec = float(ts_val) / 1_000_000_000.0
            return datetime.fromtimestamp(sec, tz=timezone.utc).isoformat(timespec="seconds")
        if isinstance(ts_val, str):
            return ts_val[:19]
        return ""

    for ts_val, line in entries:
        m = LINE_RE.match(line)
        if not m:
            continue
        scanned += 1
        if m["level"] not in BAD:
            continue
        errors += 1
        key = pattern(m["msg"])
        ts = parse_ts(ts_val) or (m["ts"] or "")[:19]

        g = groups.get(key)
        if g is None:
            groups[key] = {
                "count": 1,
                "pattern": key,
                "example": m["msg"][:200],
                "first_seen": ts,
                "last_seen": ts,
            }
        else:
            g["count"] += 1
            g["last_seen"] = ts or g["last_seen"]

    top = sorted(groups.values(), key=lambda g: g["count"], reverse=True)[:max_patterns]
    return {"lines_scanned": scanned, "error_lines": errors, "patterns": top}
