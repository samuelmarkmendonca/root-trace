from typing import Any, Dict
import docker
from app.logutil import summarize_log_text
from app.timeutil import to_epoch_seconds, TimestampInput


class DockerLogsError(Exception):
    pass


def get_error_logs(
    service: str,
    start: TimestampInput,
    end: TimestampInput,
    max_patterns: int = 10,
) -> Dict[str, Any]:
    try:
        client = docker.from_env()
        container = client.containers.get(service)
        start_sec = int(to_epoch_seconds(start))
        end_sec = int(to_epoch_seconds(end)) + 1
        raw_logs = container.logs(since=start_sec, until=end_sec, timestamps=True)
        text = raw_logs.decode("utf-8", errors="replace")
        res = summarize_log_text(text, max_patterns=max_patterns)
        res["source"] = "docker"
        return res
    except Exception as e:
        raise DockerLogsError(f"Docker logs failed: {type(e).__name__}: {e}") from e
