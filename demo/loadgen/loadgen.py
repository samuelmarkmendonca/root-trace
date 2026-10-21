import os
import random
import time
import httpx

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:8000")
INTERVAL_SECONDS = float(os.getenv("LOADGEN_INTERVAL", "0.2"))

print(f"Starting loadgen targeting {FRONTEND_URL} every {INTERVAL_SECONDS}s", flush=True)

# Loop calling POST frontend:/api/checkout every ~0.2 s, swallowing errors
with httpx.Client(timeout=3.0) as client:
    while True:
        try:
            payload = {
                "product_id": random.choice([1, 2, 3, 4, 5]),
                "qty": 1
            }
            client.post(f"{FRONTEND_URL}/api/checkout", json=payload)
        except Exception:
            # Swallow errors as specified in AGENTS.md Section 6 Stage 4
            pass
        time.sleep(INTERVAL_SECONDS)
