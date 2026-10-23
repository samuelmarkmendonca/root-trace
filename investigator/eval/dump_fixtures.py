#!/usr/bin/env python3
"""
Dumps the collected evidence for each fault in eval/faults.yaml
to tests/fixtures/<fault_id>.json so the agent and UI can be developed
without the live stack running.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
INVESTIGATOR_DIR = SCRIPT_DIR.parent
ROOT_DIR = INVESTIGATOR_DIR.parent
FIXTURES_DIR = INVESTIGATOR_DIR / "tests" / "fixtures"
FAULTS_FILE = SCRIPT_DIR / "faults.yaml"
INJECT_SCRIPT = ROOT_DIR / "scripts" / "inject_fault.py"
INVESTIGATOR_URL = "http://localhost:8000"


def run_fault_script(cmd: str) -> None:
    subprocess.run([sys.executable, str(INJECT_SCRIPT), cmd], check=True)


def load_faults_catalog() -> list[dict]:
    with open(FAULTS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("faults", [])


def dump_fault_fixture(
    fault_info: dict,
    wait_seconds: int = 50,
    settle_seconds: int = 15,
) -> Path:
    fault_id = fault_info["id"]
    investigate_svc = fault_info.get("investigate_service", "checkout")
    print(f"\n=======================================================")
    print(f"Collecting fixture for: {fault_id}")
    print(f"Target service: {investigate_svc}")
    print(f"=======================================================")

    # 1. Reset system first
    print("Resetting faults and waiting for telemetry to settle...")
    run_fault_script("reset")
    time.sleep(settle_seconds)

    # 2. Inject fault
    print(f"Injecting fault: {fault_id} ...")
    run_fault_script(fault_id)

    # 3. Wait for telemetry window
    wait_time = wait_seconds
    if fault_id == "checkout_crash":
        wait_time = 20
    elif fault_id == "db_pool_exhausted":
        wait_time = 25

    print(f"Waiting {wait_time}s for metrics and logs to propagate...")
    time.sleep(wait_time)

    # 4. Query investigator
    print(f"Querying investigator for {investigate_svc} (window_minutes=5)...")
    payload = {"service": investigate_svc, "window_minutes": 5}
    resp = httpx.post(f"{INVESTIGATOR_URL}/investigations", json=payload, timeout=30.0)
    resp.raise_for_status()
    evidence = resp.json()

    # Annotate with ground truth metadata
    evidence["fault_id"] = fault_id
    evidence["expected_root_cause_service"] = fault_info.get("expected_root_cause_service")
    evidence["expected_root_cause"] = fault_info.get("expected_root_cause")

    # 5. Save to fixtures
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out_file = FIXTURES_DIR / f"{fault_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"Saved fixture to: {out_file}")

    # 6. Reset faults again
    print("Resetting faults...")
    run_fault_script("reset")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Dump investigation fixtures for eval faults")
    parser.add_argument("--fault", help="Specific fault_id to dump (e.g. db_errors)")
    parser.add_argument("--wait", type=int, default=50, help="Wait time in seconds for telemetry window")
    args = parser.parse_args()

    faults = load_faults_catalog()
    if args.fault:
        faults = [f for f in faults if f["id"] == args.fault]
        if not faults:
            print(f"Fault '{args.fault}' not found in faults.yaml")
            sys.exit(1)

    print(f"Dumping fixtures for {len(faults)} faults...")
    for f in faults:
        dump_fault_fixture(f, wait_seconds=args.wait)

    print("\nAll requested fixtures collected successfully!")


if __name__ == "__main__":
    main()
