from contextlib import asynccontextmanager
import logging
import os
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import BaseModel

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = httpx.AsyncClient(timeout=3.0)
    logger.info("checkout service started connected to %s", DB_URL)
    yield
    await client.aclose()


app = FastAPI(title="ShopLite Checkout Service", lifespan=lifespan)


class CheckoutRequest(BaseModel):
    product_id: int
    qty: int = 1


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
async def get_products():
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
