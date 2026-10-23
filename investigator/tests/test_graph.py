from app.graph import ServiceGraph, evaluate_service_health, find_candidates


FIXTURE_SERVICES = {
    "frontend": {"container": "frontend", "depends_on": ["checkout"]},
    "checkout": {"container": "checkout", "depends_on": ["db"]},
    "db": {"container": "db", "depends_on": []},
}


def test_graph_topology():
    graph = ServiceGraph(FIXTURE_SERVICES)
    assert graph.get_downstream("frontend") == ["checkout"]
    assert graph.get_downstream("checkout") == ["db"]
    assert graph.get_downstream("db") == []

    assert graph.get_upstream("db") == ["checkout"]
    assert graph.get_upstream("checkout") == ["frontend"]
    assert graph.get_upstream("frontend") == []


def test_evaluate_service_health():
    # 1. Healthy
    healthy_metrics = {
        "error_ratio": {"baseline": 0.0, "max": 0.0, "last": 0.0},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.06, "last": 0.06},
    }
    is_h, reasons = evaluate_service_health(healthy_metrics, {"running": True, "status": "running"})
    assert is_h is True
    assert len(reasons) == 0

    # 2. High error ratio (> 0.05)
    unhealthy_errors = {
        "error_ratio": {"baseline": 0.0, "max": 0.45, "last": 0.45},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.06, "last": 0.06},
    }
    is_h, reasons = evaluate_service_health(unhealthy_errors)
    assert is_h is False
    assert any("error_ratio" in r for r in reasons)

    # 3. High latency (> 3x baseline and > 0.3s)
    unhealthy_latency = {
        "error_ratio": {"baseline": 0.0, "max": 0.0, "last": 0.0},
        "latency_p95_seconds": {"baseline": 0.05, "max": 0.85, "last": 0.85},
    }
    is_h, reasons = evaluate_service_health(unhealthy_latency)
    assert is_h is False
    assert any("latency_p95" in r for r in reasons)

    # 4. Container stopped/dead
    is_h, reasons = evaluate_service_health(
        healthy_metrics,
        {"running": False, "status": "exited", "exit_code": 137},
    )
    assert is_h is False
    assert any("Container down" in r for r in reasons)


def test_find_candidates_cascading_failure():
    # db is faulty; checkout and frontend cascade into failure
    graph = ServiceGraph(FIXTURE_SERVICES)
    graph.mark_health("db", False, {"reasons": ["error_ratio > 0.05"]})
    graph.mark_health("checkout", False, {"reasons": ["error_ratio > 0.05"]})
    graph.mark_health("frontend", False, {"reasons": ["error_ratio > 0.05"]})

    candidates = find_candidates(graph)
    assert len(candidates) == 1
    assert candidates[0]["service"] == "db"


def test_find_candidates_middle_tier_failure():
    # checkout has bad deploy (unhealthy); db is healthy; frontend cascades into failure
    graph = ServiceGraph(FIXTURE_SERVICES)
    graph.mark_health("db", True)
    graph.mark_health("checkout", False, {"reasons": ["error_ratio > 0.05"]})
    graph.mark_health("frontend", False, {"reasons": ["error_ratio > 0.05"]})

    candidates = find_candidates(graph)
    assert len(candidates) == 1
    assert candidates[0]["service"] == "checkout"


def test_find_candidates_container_down():
    # checkout container is crashed
    graph = ServiceGraph(FIXTURE_SERVICES)
    graph.mark_health("db", True)
    graph.mark_health("checkout", False)
    graph.mark_health("frontend", False)

    container_statuses = {
        "db": {"running": True, "status": "running"},
        "checkout": {"running": False, "status": "exited", "exit_code": 1},
        "frontend": {"running": True, "status": "running"},
    }

    candidates = find_candidates(graph, container_statuses)
    assert any(c["service"] == "checkout" and c["is_down"] for c in candidates)
