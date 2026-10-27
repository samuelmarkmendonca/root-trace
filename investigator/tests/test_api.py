from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_info():
    res = client.get("/info")
    assert res.status_code == 200
    data = res.json()
    assert "active_model" in data
    assert "services" in data


def test_services():
    res = client.get("/services")
    assert res.status_code == 200
    services = res.json()
    assert "checkout" in services
    assert "db" in services
    assert "frontend" in services


def test_investigations_invalid_service():
    res = client.post("/investigations", json={"service": "nope", "window_minutes": 5})
    assert res.status_code == 404


def test_investigations_async_lifecycle(monkeypatch):
    import app.service as service_mod

    monkeypatch.setattr(service_mod, "collect_metrics", lambda svc, s, e: {
        "error_ratio": {"baseline": 0.0, "max": 0.0, "last": 0.0},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.05, "last": 0.05},
    })
    monkeypatch.setattr(service_mod, "collect_logs", lambda svc, s, e: {
        "lines_scanned": 0, "error_lines": 0, "patterns": [], "source": "loki"
    })
    monkeypatch.setattr(service_mod, "get_container_status", lambda c: {
        "status": "running", "running": True, "restart_count": 0, "oom_killed": False
    })

    # 1. POST returns {id} immediately
    with patch("app.service.InvestigatorAgent") as mock_agent_cls:
        from app.agent.schema import EvidenceItem, InvestigationReport, RootCause
        mock_agent = MagicMock()
        mock_agent.run.return_value = (
            InvestigationReport(
                target_service="checkout",
                status="completed",
                summary="Database slow",
                root_causes=[
                    RootCause(
                        rank=1,
                        service="db",
                        summary="db slow",
                        confidence=0.9,
                        evidence=[EvidenceItem(tool="query_prometheus", input="", finding="p95 > 0.8s")],
                    )
                ],
            ),
            [],
        )
        mock_agent_cls.return_value = mock_agent

        res = client.post("/investigations", json={"service": "checkout", "window_minutes": 5})
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert data["service"] == "checkout"
        inv_id = data["id"]

        # 2. GET /investigations/{id} returns details
        res_get = client.get(f"/investigations/{inv_id}")
        assert res_get.status_code == 200
        inv_data = res_get.json()
        assert inv_data["id"] == inv_id
        assert inv_data["service"] == "checkout"


def test_investigations_sync_response_shape(monkeypatch):
    import app.service as service_mod

    monkeypatch.setattr(service_mod, "collect_metrics", lambda svc, s, e: {
        "error_ratio": {"baseline": 0.0, "max": 0.0, "last": 0.0},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.05, "last": 0.05},
    })
    monkeypatch.setattr(service_mod, "collect_logs", lambda svc, s, e: {
        "lines_scanned": 0, "error_lines": 0, "patterns": [], "source": "loki"
    })
    monkeypatch.setattr(service_mod, "get_container_status", lambda c: {
        "status": "running", "running": True, "restart_count": 0, "oom_killed": False
    })

    # Mock agent so sync run finishes without live LLM in unit test
    with patch("app.service.InvestigatorAgent") as mock_agent_cls:
        from app.agent.schema import EvidenceItem, InvestigationReport, RootCause
        mock_agent = MagicMock()
        mock_agent.run.return_value = (
            InvestigationReport(
                target_service="checkout",
                status="completed",
                summary="Database slow",
                root_causes=[
                    RootCause(
                        rank=1,
                        service="db",
                        summary="db slow",
                        confidence=0.9,
                        evidence=[EvidenceItem(tool="query_prometheus", input="", finding="p95 > 0.8s")],
                    )
                ],
            ),
            [],
        )
        mock_agent_cls.return_value = mock_agent

        res = client.post("/investigations", json={"service": "checkout", "window_minutes": 5, "sync": True})
        assert res.status_code == 200
        data = res.json()
        assert data["service"] == "checkout"
        assert "graph" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert "candidates" in data
        assert isinstance(data["candidates"], list)
        assert "timeline" in data
        assert isinstance(data["timeline"], list)
        assert data["report"]["root_causes"][0]["service"] == "db"
