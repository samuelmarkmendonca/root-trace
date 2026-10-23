from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


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


def test_investigations_response_shape(monkeypatch):
    # Mock collect_metrics, collect_logs, get_container_status to return without Docker/Prometheus
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "collect_metrics", lambda svc, s, e: {
        "error_ratio": {"baseline": 0.0, "max": 0.0, "last": 0.0},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.05, "last": 0.05},
    })
    monkeypatch.setattr(main_mod, "collect_logs", lambda svc, s, e: {
        "lines_scanned": 0, "error_lines": 0, "patterns": [], "source": "loki"
    })
    monkeypatch.setattr(main_mod, "get_container_status", lambda c: {
        "status": "running", "running": True, "restart_count": 0, "oom_killed": False
    })

    res = client.post("/investigations", json={"service": "checkout", "window_minutes": 5})
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
