from app.logutil import summarize_log_text, summarize_log_entries, pattern


def test_pattern_normalization():
    assert pattern("downstream returned status 502") == "downstream returned status N"
    assert pattern("142 timeouts in 10s") == "N timeouts in Ns"


def test_summarize_log_text_plain():
    text = """INFO normal operation
WARNING something unusual
ERROR connection failed to db:5432
ERROR connection failed to db:5433
CRITICAL database down
INFO back to normal
"""
    summary = summarize_log_text(text)
    assert summary["lines_scanned"] == 6
    assert summary["error_lines"] == 3
    assert len(summary["patterns"]) == 2
    top = summary["patterns"][0]
    assert top["pattern"] == "connection failed to db:N"
    assert top["count"] == 2


def test_summarize_log_text_docker_format():
    text = """2026-10-21T12:00:00.123456Z INFO normal
2026-10-21T12:00:01.123456Z ERROR downstream call failed: 502
2026-10-21T12:00:02.123456Z ERROR downstream call failed: 502
"""
    summary = summarize_log_text(text)
    assert summary["lines_scanned"] == 3
    assert summary["error_lines"] == 2
    assert len(summary["patterns"]) == 1
    p = summary["patterns"][0]
    assert p["pattern"] == "downstream call failed: N"
    assert p["count"] == 2
    assert p["first_seen"] == "2026-10-21T12:00:01"
    assert p["last_seen"] == "2026-10-21T12:00:02"


def test_summarize_log_entries_loki():
    entries = [
        ("1700000000000000000", "INFO hello"),
        ("1700000001000000000", "ERROR connection refused 127.0.0.1"),
        ("1700000005000000000", "ERROR connection refused 127.0.0.2"),
    ]
    summary = summarize_log_entries(entries)
    assert summary["lines_scanned"] == 3
    assert summary["error_lines"] == 2
    assert len(summary["patterns"]) == 1
    p = summary["patterns"][0]
    assert p["pattern"] == "connection refused N.N.N.N"
    assert p["count"] == 2
