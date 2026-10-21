#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

DB_BASE = os.getenv("DB_URL", "http://localhost:8003")
CHECKOUT_BASE = os.getenv("CHECKOUT_URL", "http://localhost:8002")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEPLOYS_FILE = ROOT_DIR / "data" / "deploys.json"


def post_request(url: str) -> None:
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            body = resp.read().decode("utf-8")
            print(f"[{resp.status}] {url} -> {body}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {url} -> {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"[ERROR] {url} -> {e}")


def inject_db_latency(ms: int = 800) -> None:
    print(f"Injecting db_latency: {ms}ms")
    post_request(f"{DB_BASE}/fault/latency?ms={ms}")


def inject_db_errors(rate: float = 0.6) -> None:
    print(f"Injecting db_errors: rate={rate}")
    post_request(f"{DB_BASE}/fault/errors?rate={rate}")


def inject_db_pool_exhausted(hold_seconds: int = 60) -> None:
    print(f"Injecting db_pool_exhausted: hold_seconds={hold_seconds}")
    post_request(f"{DB_BASE}/fault/pool?hold_seconds={hold_seconds}")


def inject_checkout_memory_leak(mb_per_request: int = 1) -> None:
    print(f"Injecting checkout_memory_leak: {mb_per_request}MB/req")
    post_request(f"{CHECKOUT_BASE}/fault/leak?mb_per_request={mb_per_request}")


def inject_checkout_crash() -> None:
    print("Injecting checkout_crash: stopping checkout container")
    subprocess.run(["docker", "stop", "checkout"], check=False)


def inject_bad_deploy() -> None:
    print("Injecting bad_deploy: checkout error_rate=0.4 and recording deploy event")
    post_request(f"{CHECKOUT_BASE}/fault/errors?rate=0.4")

    # Record deploy event
    deploy_event = {
        "time": int(time.time()),
        "service": "checkout",
        "version": "v2",
        "change": "payment_timeout_ms 2000 -> 50",
    }
    events = []
    if DEPLOYS_FILE.exists():
        try:
            with open(DEPLOYS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    events = json.loads(content)
        except Exception as e:
            print(f"Warning: could not read existing deploys.json: {e}")
            events = []

    events.append(deploy_event)
    DEPLOYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOYS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    print(f"Appended deploy event to {DEPLOYS_FILE}: {deploy_event}")


def reset_all() -> None:
    print("Resetting all faults...")
    # Make sure checkout container is running first
    subprocess.run(["docker", "start", "checkout"], check=False)
    # Wait briefly for checkout to be accessible if it was started
    time.sleep(1.0)
    post_request(f"{DB_BASE}/fault/reset")
    post_request(f"{CHECKOUT_BASE}/fault/reset")
    print("All faults reset.")


FAULTS = {
    "db_latency": inject_db_latency,
    "db_errors": inject_db_errors,
    "db_pool_exhausted": inject_db_pool_exhausted,
    "checkout_memory_leak": inject_checkout_memory_leak,
    "checkout_crash": inject_checkout_crash,
    "bad_deploy": inject_bad_deploy,
    "reset": reset_all,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in FAULTS:
        print(f"Usage: {sys.argv[0]} <fault_id>")
        print("Available fault_ids:")
        for name in FAULTS:
            print(f"  - {name}")
        sys.exit(1)

    fault_id = sys.argv[1]
    FAULTS[fault_id]()


if __name__ == "__main__":
    main()
