import json
from pathlib import Path
import pytest
import yaml

TESTS_DIR = Path(__file__).resolve().parent
INVESTIGATOR_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
FAULTS_FILE = INVESTIGATOR_DIR / "eval" / "faults.yaml"


def load_faults():
    if not FAULTS_FILE.exists():
        pytest.skip(f"faults.yaml not found at {FAULTS_FILE}")
    with open(FAULTS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("faults", [])


@pytest.fixture(params=load_faults(), ids=lambda f: f["id"])
def fault_case(request):
    return request.param


def test_fixture_integrity(fault_case):
    fault_id = fault_case["id"]
    fixture_path = FIXTURES_DIR / f"{fault_id}.json"

    if not fixture_path.exists():
        pytest.skip(f"Fixture for {fault_id} not yet generated at {fixture_path}")

    with open(fixture_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    # Core response envelope
    assert "service" in evidence
    assert "window" in evidence
    assert "metrics" in evidence
    assert "logs" in evidence
    assert "graph" in evidence
    assert "candidates" in evidence
    assert "timeline" in evidence

    # Metrics section
    metrics = evidence["metrics"]
    assert "error_ratio" in metrics
    assert "latency_p95_seconds" in metrics

    # Graph section
    graph = evidence["graph"]
    assert "nodes" in graph
    assert "edges" in graph
    assert len(graph["nodes"]) >= 3

    # Timeline section
    timeline = evidence["timeline"]
    assert isinstance(timeline, list)
    # Timeline should be sorted by epoch
    epochs = [e.get("epoch", 0) for e in timeline]
    assert epochs == sorted(epochs)

    # Pre-ranked candidates
    candidates = evidence["candidates"]
    assert isinstance(candidates, list)
    # The expected root cause service should be identified among the candidates
    expected_svc = fault_case["expected_root_cause_service"]
    candidate_services = [c.get("service") for c in candidates]

    # Node health in graph
    node_health = {n["id"]: n["health"] for n in graph["nodes"]}
    assert expected_svc in node_health
    # Expected service should either be marked unhealthy or appear in candidate list
    assert expected_svc in candidate_services or node_health[expected_svc] == "unhealthy"
