from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import httpx

SERVICE = os.getenv("SERVICE_NAME", "frontend")
CHECKOUT_URL = os.getenv("CHECKOUT_URL", "http://checkout:8000")

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
    logger.info("frontend service started connected to %s", CHECKOUT_URL)
    yield
    await client.aclose()


app = FastAPI(title="ShopLite Frontend", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/products")
async def proxy_products():
    assert client is not None
    try:
        r = await client.get(f"{CHECKOUT_URL}/products")
    except Exception as e:
        logger.error("downstream call failed: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=502, detail="downstream call failed")

    if r.status_code >= 500:
        logger.error("downstream returned status %s", r.status_code)
        raise HTTPException(status_code=502, detail=f"downstream returned status {r.status_code}")

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


@app.post("/api/checkout")
async def proxy_checkout(request: Request):
    assert client is not None
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        r = await client.post(f"{CHECKOUT_URL}/checkout", json=body)
    except Exception as e:
        logger.error("downstream call failed: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=502, detail="downstream call failed")

    if r.status_code >= 500:
        logger.error("downstream returned status %s", r.status_code)
        raise HTTPException(status_code=502, detail=f"downstream returned status {r.status_code}")

    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text)

    return r.json()


# Mount static files at root directory; html=True serves index.html for GET /
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
