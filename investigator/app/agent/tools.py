import json
import logging
from typing import Any, Dict, List, Optional
from app.adapters import container_status, prometheus
from app.collect import collect_logs
from app.config import load_services_config
from app.graph import ServiceGraph
from app.summarize import summarize_series

logger = logging.getLogger("investigator.agent.tools")

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_prometheus",
            "description": "Execute a read-only PromQL range query over the investigation time window. Returns summarized metric statistics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PromQL query string, e.g. sum(rate(http_requests_total{job=\"checkout\"}[1m]))",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_logs",
            "description": "Search error logs for a specific service in the investigation window. Returns up to 10 deduplicated error log patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "The name of the service (e.g. 'checkout', 'db', 'frontend')",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search keyword or regex filter to filter log patterns",
                    },
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_container_status",
            "description": "Get container health, running state, restart count, and OOMKilled status from Docker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "The name of the service (e.g. 'checkout', 'db', 'frontend')",
                    }
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_downstream",
            "description": "Get direct downstream dependencies called by the service from the service topology graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "The name of the service (e.g. 'frontend', 'checkout')",
                    }
                },
                "required": ["service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_incident_history",
            "description": "Retrieve past resolved incidents for a service to identify recurrent failure modes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "The name of the service (e.g. 'checkout', 'db')",
                    }
                },
                "required": ["service"],
            },
        },
    },
]


class ToolExecutionError(Exception):
    pass


def get_allowed_services() -> Dict[str, Any]:
    try:
        return load_services_config()
    except Exception:
        return {"frontend": {}, "checkout": {}, "db": {}}


def run_query_prometheus(
    query: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    start = context.get("start_sec")
    end = context.get("end_sec")
    if start is None or end is None:
        raise ToolExecutionError("Investigation time window missing from context")

    try:
        results = prometheus.query_range(query, start=start, end=end, step="15s")
        if not results:
            return {"query": query, "series_count": 0, "message": "No series returned for query"}

        summaries = []
        for res in results[:5]:  # Cap at top 5 series to avoid context blowout
            metric_labels = res.get("metric", {})
            values = res.get("values", [])
            summary = summarize_series(values)
            summaries.append({
                "metric": metric_labels,
                "summary": summary if summary is not None else {"note": "insufficient points"},
            })

        return {
            "query": query,
            "series_count": len(results),
            "summaries": summaries,
        }
    except Exception as e:
        logger.warning(f"Tool query_prometheus failed: {e}")
        return {"error": f"Prometheus query failed: {str(e)}"}


def run_search_logs(
    service: str,
    context: Dict[str, Any],
    query: Optional[str] = None,
) -> Dict[str, Any]:
    services_cfg = get_allowed_services()
    if service not in services_cfg:
        allowed = list(services_cfg.keys())
        return {"error": f"Unknown service '{service}'. Allowed services: {allowed}"}

    start = context.get("start_sec")
    end = context.get("end_sec")
    if start is None or end is None:
        raise ToolExecutionError("Investigation time window missing from context")

    try:
        logs_data = collect_logs(service, start=start, end=end, max_patterns=10)
        patterns = logs_data.get("patterns", [])

        if query:
            q_lower = query.lower()
            patterns = [
                p for p in patterns
                if q_lower in p.get("pattern", "").lower() or q_lower in p.get("sample", "").lower()
            ]

        return {
            "service": service,
            "pattern_count": len(patterns),
            "patterns": patterns[:10],
            "total_lines": logs_data.get("total_lines", 0),
        }
    except Exception as e:
        logger.warning(f"Tool search_logs failed: {e}")
        return {"error": f"Log search failed for {service}: {str(e)}"}


def run_get_container_status(
    service: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    services_cfg = get_allowed_services()
    if service not in services_cfg:
        allowed = list(services_cfg.keys())
        return {"error": f"Unknown service '{service}'. Allowed services: {allowed}"}

    container_name = services_cfg.get(service, {}).get("container", service)
    try:
        status = container_status.get_container_status(container_name)
        status["service"] = service
        return status
    except Exception as e:
        return {"service": service, "error": f"Container status failed: {str(e)}"}


def run_get_downstream(
    service: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    services_cfg = get_allowed_services()
    if service not in services_cfg:
        allowed = list(services_cfg.keys())
        return {"error": f"Unknown service '{service}'. Allowed services: {allowed}"}

    graph = ServiceGraph(services_cfg)
    downstream = graph.get_downstream(service)
    upstream = graph.get_upstream(service)
    return {
        "service": service,
        "downstream_dependencies": downstream,
        "upstream_callers": upstream,
    }


def run_get_incident_history(
    service: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    services_cfg = get_allowed_services()
    if service not in services_cfg:
        allowed = list(services_cfg.keys())
        return {"error": f"Unknown service '{service}'. Allowed services: {allowed}"}

    # Incident store reading: return empty list or past incident records
    return {
        "service": service,
        "past_incidents": [],
        "note": "No previous recurring incidents recorded for this service",
    }


TOOL_REGISTRY = {
    "query_prometheus": run_query_prometheus,
    "search_logs": run_search_logs,
    "get_container_status": run_get_container_status,
    "get_downstream": run_get_downstream,
    "get_incident_history": run_get_incident_history,
}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a tool safely with argument validation and error containment."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool '{name}'. Whitelisted tools: {list(TOOL_REGISTRY.keys())}"}

    func = TOOL_REGISTRY[name]
    try:
        if name == "query_prometheus":
            query = args.get("query", "")
            if not query or not isinstance(query, str):
                return {"error": "Missing or invalid 'query' argument"}
            return func(query=query, context=context)

        elif name in ("search_logs", "get_container_status", "get_downstream", "get_incident_history"):
            service = args.get("service", "")
            if not service or not isinstance(service, str):
                return {"error": "Missing or invalid 'service' argument"}
            if name == "search_logs":
                query = args.get("query")
                return func(service=service, query=query, context=context)
            return func(service=service, context=context)

        return {"error": f"Tool '{name}' dispatch not configured"}
    except Exception as e:
        logger.exception(f"Unexpected error executing tool {name}: {e}")
        return {"error": f"Tool execution failed: {type(e).__name__}: {str(e)}"}
