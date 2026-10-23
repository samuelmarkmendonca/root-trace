import pytest
from unittest.mock import MagicMock, patch
from app.agent.tools import (
    TOOL_DEFINITIONS,
    TOOL_REGISTRY,
    execute_tool,
    run_get_container_status,
    run_get_downstream,
    run_get_incident_history,
    run_query_prometheus,
    run_search_logs,
)


def test_tool_definitions_and_registry_match():
    def_names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert def_names == set(TOOL_REGISTRY.keys())
    assert "query_prometheus" in def_names
    assert "search_logs" in def_names
    assert "get_container_status" in def_names
    assert "get_downstream" in def_names
    assert "get_incident_history" in def_names


def test_execute_unknown_tool():
    res = execute_tool("rm_rf_everything", {}, {"start_sec": 100, "end_sec": 200})
    assert "error" in res
    assert "Unknown tool" in res["error"]


def test_execute_unknown_service():
    context = {"start_sec": 100, "end_sec": 200}
    res = execute_tool("get_container_status", {"service": "malicious_service"}, context)
    assert "error" in res
    assert "Unknown service" in res["error"]

    res_logs = execute_tool("search_logs", {"service": "hacked"}, context)
    assert "error" in res_logs
    assert "Unknown service" in res_logs["error"]


def test_execute_missing_args():
    context = {"start_sec": 100, "end_sec": 200}
    res1 = execute_tool("query_prometheus", {}, context)
    assert "error" in res1
    assert "query" in res1["error"]

    res2 = execute_tool("search_logs", {}, context)
    assert "error" in res2
    assert "service" in res2["error"]


def test_get_downstream():
    context = {"start_sec": 100, "end_sec": 200}
    res = execute_tool("get_downstream", {"service": "frontend"}, context)
    assert res["service"] == "frontend"
    assert "checkout" in res["downstream_dependencies"]
    assert res["upstream_callers"] == []

    res_db = execute_tool("get_downstream", {"service": "db"}, context)
    assert res_db["downstream_dependencies"] == []
    assert "checkout" in res_db["upstream_callers"]


def test_get_incident_history():
    context = {"start_sec": 100, "end_sec": 200}
    res = execute_tool("get_incident_history", {"service": "checkout"}, context)
    assert res["service"] == "checkout"
    assert "past_incidents" in res


@patch("app.adapters.prometheus.query_range")
def test_query_prometheus_tool(mock_query):
    mock_query.return_value = [
        {
            "metric": {"job": "checkout"},
            "values": [[100, "1.0"], [115, "1.5"], [130, "2.0"]],
        }
    ]
    context = {"start_sec": 100, "end_sec": 200}
    res = execute_tool("query_prometheus", {"query": "rate(http_requests_total[1m])"}, context)
    assert res["series_count"] == 1
    assert len(res["summaries"]) == 1
    assert "summary" in res["summaries"][0]
    assert res["summaries"][0]["summary"]["min"] == 1.0
    assert res["summaries"][0]["summary"]["max"] == 2.0


@patch("app.agent.tools.collect_logs")
def test_search_logs_tool(mock_logs):
    mock_logs.return_value = {
        "patterns": [
            {"pattern": "downstream returned status 502", "count": 10, "sample": "downstream returned status 502"},
            {"pattern": "internal error in db", "count": 5, "sample": "internal error in db"},
        ],
        "total_lines": 15,
    }
    context = {"start_sec": 100, "end_sec": 200}
    res = execute_tool("search_logs", {"service": "checkout", "query": "502"}, context)
    assert res["service"] == "checkout"
    assert res["pattern_count"] == 1
    assert "502" in res["patterns"][0]["pattern"]
