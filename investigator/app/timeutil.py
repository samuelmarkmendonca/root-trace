from datetime import datetime, timezone
from typing import Union

TimestampInput = Union[int, float, datetime, str]


def now_seconds() -> float:
    return datetime.now(timezone.utc).timestamp()


def to_epoch_seconds(val: TimestampInput) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.timestamp()
    if isinstance(val, str):
        # Handle digits or ISO string
        try:
            return float(val)
        except ValueError:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    raise ValueError(f"Cannot convert {val!r} to epoch seconds")


def to_epoch_nanoseconds(val: TimestampInput) -> int:
    sec = to_epoch_seconds(val)
    return int(sec * 1_000_000_000)


def to_epoch_microseconds(val: TimestampInput) -> int:
    sec = to_epoch_seconds(val)
    return int(sec * 1_000_000)


def seconds_to_iso(sec: Union[int, float]) -> str:
    return datetime.fromtimestamp(float(sec), tz=timezone.utc).isoformat(timespec="seconds")


def nanoseconds_to_iso(ns: Union[int, str]) -> str:
    sec = float(ns) / 1_000_000_000.0
    return seconds_to_iso(sec)


def compute_window(window_minutes: int, end_time: TimestampInput | None = None) -> tuple[float, float]:
    end_sec = to_epoch_seconds(end_time) if end_time is not None else now_seconds()
    start_sec = end_sec - (window_minutes * 60.0)
    return start_sec, end_sec
