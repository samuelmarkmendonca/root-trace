import logging
from typing import Any, Dict
from app.adapters import dockerlogs, loki, prometheus
from app.summarize import METRICS, summarize_series
from app.timeutil import TimestampInput, to_epoch_seconds

logger = logging.getLogger("investigator.collect")


def collect_metrics(
    service: str,
    start: TimestampInput,
    end: TimestampInput,
    step: str = "15s",
) -> Dict[str, Any]:
    start_sec = to_epoch_seconds(start)
    end_sec = to_epoch_seconds(end)
    metrics_summary: Dict[str, Any] = {}

    for metric_name, cfg in METRICS.items():
        query = cfg["query"].replace("__SVC__", service)
        min_delta = cfg.get("min_delta", 0.0)
        try:
            results = prometheus.query_range(query, start_sec, end_sec, step=step)
            if not results:
                metrics_summary[metric_name] = {"note": "no data in this window"}
                continue

            values = results[0].get("values", [])
            summary = summarize_series(values, min_delta=min_delta)
            if summary is None:
                metrics_summary[metric_name] = {"note": "no data in this window"}
            else:
                metrics_summary[metric_name] = summary
        except Exception as e:
            logger.warning(f"Failed to query metric {metric_name} for {service}: {e}")
            metrics_summary[metric_name] = {"error": str(e)}

    return metrics_summary


def collect_logs(
    service: str,
    start: TimestampInput,
    end: TimestampInput,
    max_patterns: int = 10,
) -> Dict[str, Any]:
    loki_err: str | None = None
    try:
        return loki.get_error_logs(service, start, end, max_patterns=max_patterns)
    except Exception as e:
        loki_err = str(e)
        logger.info(f"Loki error logs failed for {service}, falling back to Docker SDK: {e}")

    try:
        return dockerlogs.get_error_logs(service, start, end, max_patterns=max_patterns)
    except Exception as e:
        docker_err = str(e)
        logger.warning(f"Docker logs fallback failed for {service}: {e}")
        return {"error": f"Loki failed ({loki_err}); Docker fallback failed ({docker_err})"}
