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
