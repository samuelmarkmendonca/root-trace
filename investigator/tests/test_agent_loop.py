import json
from unittest.mock import MagicMock
import pytest
from app.agent.loop import InvestigatorAgent
from app.agent.schema import AgentStepEvent, InvestigationReport


@pytest.fixture
def sample_evidence():
    return {
        "service": "checkout",
        "window": {
            "start": "2026-10-23T12:00:00Z",
            "end": "2026-10-23T12:15:00Z",
            "minutes": 15,
        },
        "candidates": ["db"],
        "graph": {
            "nodes": [
                {"id": "frontend", "health": "healthy"},
                {"id": "checkout", "health": "unhealthy"},
                {"id": "db", "health": "unhealthy"},
            ],
            "edges": [
                {"from": "frontend", "to": "checkout"},
                {"from": "checkout", "to": "db"},
            ],
        },
        "timeline": [
            {"timestamp": 100, "service": "db", "type": "metric_jump", "description": "p95 jumped to 0.95s"}
        ],
        "metrics": {"error_ratio": {"max": 0.5}},
        "logs": {"patterns": [{"pattern": "downstream 502", "count": 10}]},
    }


def test_agent_tool_loop_with_tool_call(sample_evidence):
    # Step 1: Model requests a tool call to search_logs for db
    msg_1 = {
        "role": "assistant",
        "content": "Let me search logs for db",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "arguments": json.dumps({"service": "db", "query": "error"}),
                },
            }
        ],
    }

    # Step 2: Model returns final report
    msg_2 = {
        "role": "assistant",
        "content": json.dumps({
            "target_service": "checkout",
            "status": "completed",
            "summary": "Database internal errors caused checkout failure",
            "root_causes": [
                {
                    "rank": 1,
                    "service": "db",
                    "summary": "Database returned 500 internal errors",
                    "confidence": 0.95,
                    "evidence": [
                        {
                            "tool": "search_logs",
                            "input": "service='db'",
                            "finding": "injected fault: internal error",
                        }
                    ],
                }
            ],
        }),
    }

    mock_client = MagicMock()
    mock_client.complete.side_effect = [msg_1, msg_2]

    agent = InvestigatorAgent(client=mock_client, max_steps=4)
    emitted_events = []
    report, events = agent.run(sample_evidence, on_event=emitted_events.append)

    assert isinstance(report, InvestigationReport)
    assert report.target_service == "checkout"
    assert len(report.root_causes) == 1
    assert report.root_causes[0].service == "db"
    assert report.root_causes[0].confidence == 0.95

    # Verify event types
    event_types = [e.type for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "final_answer" in event_types
    assert len(emitted_events) == len(events)


def test_agent_retry_on_parse_failure(sample_evidence):
    # Step 1: Model outputs malformed/incomplete JSON (missing evidence)
    msg_1 = {
        "role": "assistant",
        "content": '{"root_causes": [{"service": "db", "confidence": 0.5}]}',
    }

    # Step 2 (retry): Model outputs corrected JSON matching schema
    msg_2 = {
        "role": "assistant",
        "content": json.dumps({
            "target_service": "checkout",
            "status": "completed",
            "summary": "Database crashed",
            "root_causes": [
                {
                    "rank": 1,
                    "service": "db",
                    "summary": "Database connection pool exhausted",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "tool": "container_status",
                            "input": "service='db'",
                            "finding": "connection pool exhausted",
                        }
                    ],
                }
            ],
        }),
    }

    mock_client = MagicMock()
    mock_client.complete.side_effect = [msg_1, msg_2]

    agent = InvestigatorAgent(client=mock_client, max_steps=4)
    report, events = agent.run(sample_evidence)

    assert isinstance(report, InvestigationReport)
    assert report.root_causes[0].service == "db"

    # Verify retry error event was emitted
    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) >= 1
    assert "schema" in error_events[0].content.lower()


def test_agent_fallback_on_max_steps(sample_evidence):
    # Model keeps producing empty or unparseable text
    msg = {"role": "assistant", "content": "I am still thinking and not ready to answer."}
    mock_client = MagicMock()
    mock_client.complete.return_value = msg

    agent = InvestigatorAgent(client=mock_client, max_steps=2)
    report, events = agent.run(sample_evidence)

    assert isinstance(report, InvestigationReport)
    assert report.target_service == "checkout"
    assert report.root_causes[0].service == "db"  # Fallback uses pre-ranker candidate
