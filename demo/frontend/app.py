import logging
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Logging format matching AGENTS.md Section 7: "LEVEL message" on stdout with PYTHONUNBUFFERED=1
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("frontend")

app = FastAPI(title="ShopLite Frontend")


@app.on_event("startup")
def on_startup():
    logger.info("frontend service started on port 8001")


@app.get("/health")
def health():
    return {"status": "ok"}


# Mount static files at root directory; html=True serves index.html for GET /
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
