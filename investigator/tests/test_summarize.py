from app.summarize import summarize_series


def test_summarize_series_flat():
    # 20 points of 1.0 at 15s intervals
    values = [(1000 + i * 15, "1.0") for i in range(20)]
    res = summarize_series(values, min_delta=0.5, jump_factor=2.0)
    assert res is not None
    assert res["baseline"] == 1.0
    assert res["min"] == 1.0
    assert res["max"] == 1.0
    assert res["avg"] == 1.0
    assert res["jump_at"] is None
    assert res["points"] == 20


def test_summarize_series_nan_only():
    values = [(1000, "NaN"), (1015, "inf"), (1030, float("nan")), (1045, "invalid")]
    res = summarize_series(values)
    assert res is None


def test_summarize_series_jump():
    # 10 points at 0.05, then 10 points at 0.9
    values = [(1000 + i * 15, "0.05") for i in range(10)] + [
        (1000 + (10 + i) * 15, "0.9") for i in range(10)
    ]
    res = summarize_series(values, min_delta=0.05, jump_factor=2.0)
    assert res is not None
    assert res["baseline"] == 0.05
    assert res["max"] == 0.9
    assert res["jump_at"] is not None
    # First point after baseline slice (n_base = 20//4 = 5) where v - baseline > 0.05 and v > 0.1
    # is at index 10 (t = 1150)
    assert res["points"] == 20
