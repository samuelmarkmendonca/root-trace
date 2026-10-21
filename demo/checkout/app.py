import asyncio
from contextlib import asynccontextmanager
import logging
import os
import random
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel

from common.observability import setup_observability

SERVICE = os.getenv("SERVICE_NAME", "checkout")
DB_URL = os.getenv("DB_URL", "http://db:8000")

# Logging format matching AGENTS.md Section 7: "LEVEL message" on stdout with PYTHONUNBUFFERED=1
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(SERVICE)

client: Optional[httpx.AsyncClient] = None

# Fault state
faults = {
    "latency_ms": 0,
    "error_rate": 0.0,
    "leak_mb": 0,
}
leak_memory: list[bytearray] = []


async def apply_faults():
    if faults["latency_ms"]:
        await asyncio.sleep(faults["latency_ms"] / 1000)
    if faults["leak_mb"]:
        leak_memory.append(bytearray(faults["leak_mb"] * 1024 * 1024))
    if faults["error_rate"] > 0 and random.random() < faults["error_rate"]:
        logger.error("injected fault: internal error while handling request")
        raise HTTPException(status_code=500, detail="injected fault: internal error while handling request")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = httpx.AsyncClient(timeout=3.0)
    logger.info("checkout service started connected to %s", DB_URL)
    yield
    await client.aclose()


app = FastAPI(title="ShopLite Checkout Service", lifespan=lifespan)
setup_observability(app)


class CheckoutRequest(BaseModel):
    product_id: int
    qty: int = 1


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Fault endpoints ---

@app.post("/fault/latency")
async def fault_latency(ms: int = 800):
    faults["latency_ms"] = ms
    logger.warning("fault set: latency_ms=%d", ms)
    return {"status": "ok", "latency_ms": ms}


@app.post("/fault/errors")
async def fault_errors(rate: float = 0.4):
    faults["error_rate"] = rate
    logger.warning("fault set: error_rate=%.2f", rate)
    return {"status": "ok", "error_rate": rate}


@app.post("/fault/leak")
async def fault_leak(mb_per_request: int = 1):
    faults["leak_mb"] = mb_per_request
    logger.warning("fault set: leak_mb=%d", mb_per_request)
    return {"status": "ok", "leak_mb": mb_per_request}


@app.post("/fault/reset")
async def fault_reset():
    faults["latency_ms"] = 0
    faults["error_rate"] = 0.0
    faults["leak_mb"] = 0
    leak_memory.clear()
    logger.warning("fault reset: all faults cleared")
    return {"status": "ok"}


# --- Product & Checkout endpoints ---

@app.get("/products")
async def get_products():
    await apply_faults()
    assert client is not None
    try:
        r = await client.get(f"{DB_URL}/products")
    except Exception as e:
        logger.error("downstream call failed: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=502, detail="downstream call failed")

    if r.status_code >= 500:
        logger.error("downstream returned status %s", r.status_code)
        raise HTTPException(status_code=502, detail=f"downstream returned status {r.status_code}")

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.post("/checkout")
async def checkout(req: CheckoutRequest):
    await apply_faults()
    assert client is not None

    # 1. Check stock via db: GET /products/{id}
    try:
        r = await client.get(f"{DB_URL}/products/{req.product_id}")
    except Exception as e:
        logger.error("downstream call failed: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=502, detail="downstream call failed")

    if r.status_code >= 500:
        logger.error("downstream returned status %s", r.status_code)
        raise HTTPException(status_code=502, detail=f"downstream returned status {r.status_code}")

    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Product not found")

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    product = r.json()
    if product.get("stock", 0) < req.qty:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    # 2. Create order via db: POST /orders
    order_payload = {
        "product_id": req.product_id,
        "qty": req.qty,
        "total_price": round(product["price"] * req.qty, 2)
    }
    try:
        r_order = await client.post(f"{DB_URL}/orders", json=order_payload)
    except Exception as e:
        logger.error("downstream call failed: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=502, detail="downstream call failed")

    if r_order.status_code >= 500:
        logger.error("downstream returned status %s", r_order.status_code)
        raise HTTPException(status_code=502, detail=f"downstream returned status {r_order.status_code}")

    if r_order.status_code not in (200, 201):
        raise HTTPException(status_code=r_order.status_code, detail=r_order.text)

    order_data = r_order.json()
    logger.info("checkout completed order %s for product %d", order_data["order_id"], req.product_id)
    return {
        "order_id": order_data["order_id"],
        "product_id": req.product_id,
        "qty": req.qty,
        "total_price": order_data.get("total_price"),
        "status": "completed"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
