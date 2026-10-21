# root-trace

Autonomous incident investigation engine for microservice architectures. Given a reported service anomaly and time window, root-trace correlates metrics, logs, container state, and deployment events to identify and rank probable root causes.

## Overview

Traditional incident troubleshooting requires manual correlation across distributed dashboards, logs, and container statuses. root-trace automates this process through a two-phase architecture:

1. Deterministic Telemetry Processing: Collects time-series metrics from Prometheus, error streams from Loki (with Docker SDK fallback), container lifecycles via the Docker API, and change records from deployment logs. Constructs an incident timeline and evaluates service health against an in-memory dependency graph to pre-rank candidate fault origins.
2. Read-Only Hypothesis Verification: An LLM agent reasons over pre-ranked candidates and queries telemetry stores using restricted, read-only diagnostic tools to confirm or refute failure hypotheses.

The investigator operates strictly out-of-band: it never modifies application code, injects runtime agents, or accepts arbitrary execution commands.

## Architecture

```
 browser -> frontend -> checkout -> db (SQLite)     [Demo Application: ShopLite]
 loadgen ->    |            |          |
               +--- /metrics ----------+
                         |
                    Prometheus <-----------+
 container stdout -> Alloy -> Loki <-------+
 docker.sock (ro) -------------------------+
 data/deploys.json (ro) -------------------+
                                       investigator (FastAPI)
                                        - Adapters (Prometheus, Loki, Docker)
                                        - Summarizers (Metric change detection, Log dedup)
                                        - Graph, Timeline & Pre-ranker
                                        - LLM Agent (Read-only tool loop)
                                        - Web UI (Static HTML/JS, SSE stream)
```

## System Components

- Demo Application (ShopLite):
  - frontend (port 8001): Web interface, checkout proxy, fault administration.
  - checkout (port 8002): Order orchestration, inventory verification.
  - db (port 8003): SQLite storage with simulated connection pool limits.
  - loadgen: Generates synthetic background traffic.
- Telemetry & Infrastructure:
  - Prometheus (port 9090): Scrapes HTTP latency, throughput, and error rates every 5 seconds.
  - Grafana Loki (port 3100): Aggregates container stdout/stderr.
  - Grafana Alloy (port 12345): Ships Docker container logs to Loki.
- Investigator (port 8000):
  - Core API and embedded static web dashboard.
  - Ollama integration on the host (port 11434) using tool-calling models (e.g., Qwen).

## Port Allocations

| Port | Service | Description |
|---|---|---|
| 8000 | investigator | Investigator Web UI and REST API |
| 8001 | frontend | ShopLite web storefront |
| 8002 | checkout | Checkout service |
| 8003 | db | Database service |
| 9090 | Prometheus | Time-series metrics backend |
| 3100 | Loki | Log aggregation backend |
| 12345 | Alloy | Alloy telemetry agent management interface |
| 11434 | Ollama | Host LLM runner (OpenAI-compatible endpoint) |

## Fault Catalog (Evaluation Matrix)

The system includes a fault injection CLI (`scripts/inject_fault.py`) simulating canonical failure modes:

| Fault ID | Trigger Mechanism | Expected Propagation | Root Cause |
|---|---|---|---|
| db_latency | Injected sleep in DB handlers | DB p95 latency spikes; propagates to checkout and frontend | Database slow query latency |
| db_errors | Synthetic 500 responses from DB | Cascading 502 Bad Gateway responses upstream | Database internal errors |
| db_pool_exhausted | Exhausts connection pool semaphore | DB returns 503 Service Unavailable | Database connection pool exhaustion |
| checkout_memory_leak | Retains memory per request | Container triggers OOMKilled via Docker memory limit | Memory leak causing crash loops |
| checkout_crash | Stops checkout container | Frontend raises ConnectError (502) | Checkout container down |
| bad_deploy | Injects errors + appends deploy record | Checkout error rate correlates with deploy timestamp | Faulty application deployment |

## Development Stages

Development follows a strict gated progression:
- Stage 0: Repository scaffold, compose skeleton, and environment configuration.
- Stage 1: ShopLite frontend presentation layer.
- Stage 2: ShopLite client-side state and mock fault panel.
- Stage 3: ShopLite backend services (checkout and db) with real database persistence.
- Stage 4: Prometheus metric instrumentation, fault endpoints, and loadgen.
- Stage 5: Prometheus server deployment and metric scrape validation.
- Stage 6: Loki log ingestion pipeline via Grafana Alloy.
- Stage 7: Investigator deterministic data path (adapters, metric summarization, log deduplication).
- Stage 8: Graph engine, timeline synthesis, and candidate pre-ranker.
- Stage 9: Evaluation harness and ground-truth telemetry fixtures.
- Stage 10: LLM integration and read-only diagnostic tool loop.
- Stage 11: SSE streaming API and browser dashboard.
- Stage 12: Automated evaluation suite against the fault matrix.

## Running the Project

Prerequisites:
- Docker and Docker Compose v2
- Python 3.12 (for local development and running unit tests)
- Ollama (installed on host machine for Stage 10+)

Start all services:
```sh
docker compose up --build -d
```

Verify service status:
```sh
docker compose ps
```

Local testing (no Docker required for core algorithmic units):
```sh
cd investigator
pytest
```

## Telemetry & Fault Verification (Stage 7)

Query the investigator endpoint for a service:
```sh
curl.exe -s --json '{"service":"checkout","window_minutes":5}' http://localhost:8000/investigations
```

Inject a fault (e.g. database errors):
```sh
python scripts/inject_fault.py db_errors
```
Wait ~60 seconds for the Prometheus scrape interval and 1m rate window, then re-query:
```sh
curl.exe -s --json '{"service":"checkout","window_minutes":5}' http://localhost:8000/investigations
curl.exe -s --json '{"service":"db","window_minutes":5}' http://localhost:8000/investigations
```

Test database latency injection (800ms):
```sh
python scripts/inject_fault.py db_latency
```

Reset all faults:
```sh
python scripts/inject_fault.py reset
```
