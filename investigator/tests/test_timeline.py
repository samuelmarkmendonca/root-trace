from app.timeline import build_timeline


def test_build_timeline_merge_and_sort():
    # Base timestamp: 1700000000 (2023-11-14T22:13:20+00:00)
    t0 = 1700000000.0

    # 1. Deploy at t0 + 10s
    deploys = [
        {
            "time": t0 + 10,
            "service": "checkout",
            "version": "v2",
            "change": "payment_timeout 50ms",
        }
    ]

    # 2. Metric jump at t0 + 25s
    metrics_by_service = {
        "checkout": {
            "error_ratio": {
                "baseline": 0.0,
                "max": 0.6,
                "jump_at": "2023-11-14T22:13:45+00:00",  # t0 + 25s
            }
        }
    }

    # 3. Log pattern first seen at t0 + 20s
    logs_by_service = {
        "checkout": {
            "patterns": [
                {
                    "pattern": "downstream returned status N",
                    "count": 50,
                    "first_seen": "2023-11-14T22:13:40+00:00",  # t0 + 20s
                }
            ]
        }
    }

    # 4. Container restart at t0 + 50s
    container_statuses = {
        "checkout": {
            "running": True,
            "status": "running",
            "restart_count": 1,
            "started_at": "2023-11-14T22:14:10+00:00",  # t0 + 50s
        }
    }

    timeline = build_timeline(
        metrics_by_service,
        logs_by_service,
        container_statuses,
        deploys,
        start_sec=t0,
        end_sec=t0 + 100,
    )

    assert len(timeline) == 4
    # Check chronological ordering:
    # 1st: Deploy (+10s)
    assert timeline[0]["type"] == "deploy"
    assert timeline[0]["service"] == "checkout"
    # 2nd: Log pattern (+20s)
    assert timeline[1]["type"] == "log_pattern"
    assert "downstream returned status N" in timeline[1]["description"]
    # 3rd: Metric jump (+25s)
    assert timeline[2]["type"] == "metric_jump"
    assert "error_ratio" in timeline[2]["description"]
    # 4th: Container restart (+50s)
    assert timeline[3]["type"] == "container_restart"
    assert timeline[3]["service"] == "checkout"


def test_build_timeline_window_filtering():
    t0 = 1700000000.0
    deploys = [
        {"time": t0 - 2000, "service": "db", "change": "very old deploy"},
        {"time": t0 + 30, "service": "db", "change": "recent deploy"},
    ]

    timeline = build_timeline(
        {},
        {},
        {},
        deploys,
        start_sec=t0,
        end_sec=t0 + 60,
    )

    assert len(timeline) == 1
    assert timeline[0]["description"] == "Deploy: recent deploy"
