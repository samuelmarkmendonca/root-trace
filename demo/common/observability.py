import time
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
UNTRACKED = {"/metrics", "/health", "/docs", "/openapi.json"}


def setup_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def track(request: Request, call_next):
        if request.url.path in UNTRACKED:
            return await call_next(request)
        start, status = time.perf_counter(), 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            REQUESTS.labels(request.method, request.url.path, str(status)).inc()
            LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - start)

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
