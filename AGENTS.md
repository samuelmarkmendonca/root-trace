# AGENTS.md: Incident Investigator (build instructions for the coding agent)

Read this whole file before writing any code. Build **one stage at a time**, in order. Do not skip ahead, do not add features that are not listed.

## 0. How you must work

1. Work in **stages** (Section 6). Each stage has a *Gate*: commands you run and the exact result you must see.
2. After finishing a stage: run its Gate, paste the real output in your reply, make one git commit (message given per stage), then **stop and wait** for the human to say "next".
3. If a Gate fails, debug it (Section 8 lists known problems) and rerun. Never move on with a failing Gate.
4. Keep everything **simple**. This is a student project with a 2 week build budget. Prefer 40 plain lines over a clever abstraction.
5. Never use `:latest` image tags. Pin an exact tag you have verified exists on Docker Hub / the vendor docs, and write it in the compose file.
6. Items marked **[UNVERIFIED]** were designed but never run by the person who wrote this file. Verify them against the vendor's current docs before relying on them. Items marked **[VERIFIED]** were run and worked.
7. Never commit secrets. LLM endpoint and keys come from environment variables.

## 1. What we are building

An **autonomous incident investigator**. Given "service X is misbehaving between T1 and T2", it:

1. collects metrics, logs (and later traces, deploy events) for that window,
2. builds an incident timeline and a service dependency graph,
3. generates root-cause hypotheses with an LLM,
4. validates them by calling **read-only** diagnostic tools (PromQL query, log search, container status),
5. returns ranked root causes, each with evidence (tool, input, finding).

Goal: reduce incident investigation from hours of manual correlation to minutes.

The investigator **never touches the target app's code**. It reads the telemetry stores (Prometheus, Loki) and read-only infra APIs (Docker). The LLM never connects to anything: it can only ask our Python code to run whitelisted tools.

Build order principle: **deterministic code first, LLM last.** Timeline, graph, health, candidate ranking are plain code. The LLM only reasons over their output.

## 2. Decisions already made (do not revisit)

| Topic | Decision |
|---|---|
| Backend language | Python 3.12 + FastAPI |
| Frontend | Plain HTML/CSS/JS served by FastAPI `StaticFiles` from the same container (no Node build, no React). Graph drawn with `vis-network` or Cytoscape.js from a CDN. |
| Target system | Our **own** tiny shop app (3 services), not the OpenTelemetry Demo (too heavy, user also runs a local LLM) |
| Metrics | App exposes `/metrics` (prometheus_client), Prometheus scrapes it |
| Logs | Containers log to stdout. **Alloy ships them to Loki.** Investigator queries Loki. Docker SDK log reading is the fallback adapter. |
| Traces / OTel | **Later (Stage 13).** Until then the dependency graph is a hand-written `services.yaml` |
| Graph | `networkx` in memory behind a small interface. Neo4j is a later optional swap. |
| RAG / vector DB | **Skipped.** Past-incident memory is done by saving incident records and exposing a `get_incident_history` tool |
| Kubernetes | Skipped. Docker Compose only. Infra signals come from the Docker API / cAdvisor |
| LLM | Any **OpenAI-compatible** endpoint behind one `llm.py` wrapper. Default: Ollama running Qwen locally. User has no API keys. Users who ship/run this bring their own endpoint via `.env`. |
| Shipping | Self-hosted: `docker compose up` brings everything up. No hosted service, no accounts, no auth. |
| Cut order if time runs out | RAG, then Neo4j, then Kubernetes, then OTel, then VS Code extension |

## 3. Software list

Pin exact versions when you write the compose file. Check docs for current stable tags.

| Software | Role | Notes |
|---|---|---|
| Docker + Docker Compose v2 | Runs everything | User may be on Windows/Mac (Docker Desktop). Avoid bash-only tooling in docs; give Windows-safe commands. |
| Python 3.12 | Investigator + demo app | `python:3.12-slim` base image |
| FastAPI, uvicorn | HTTP APIs | |
| httpx | Outbound HTTP (sync in investigator, async in demo app) | |
| prometheus-client | Metrics in the demo app | **[VERIFIED]** |
| pydantic, pydantic-settings | Validation and env config | |
| pyyaml | Reads `services.yaml` | |
| docker (Python SDK) | Container logs/status fallback | needs `/var/run/docker.sock` mounted read-only |
| networkx | Dependency graph | Stage 6 |
| pytest | Tests | |
| Prometheus | Metrics store. Image `prom/prometheus:v2.55.1` | **[VERIFIED]** version |
| Loki | Log store. Image `grafana/loki:<pin a 3.x tag>` | **[UNVERIFIED]** |
| Grafana Alloy | Ships Docker container logs to Loki. Image `grafana/alloy:<pin>` | **[UNVERIFIED]**. Use Alloy, not Promtail (Promtail is deprecated). |
| cAdvisor (optional, Stage 5) | Container CPU/memory/restarts for Prometheus | **[UNVERIFIED]** |
| Grafana (optional) | Dashboards for debugging and demo screenshots. Investigator never calls it. | |
| Ollama + Qwen | Local LLM (runs on the **host**, not in compose) | Stage 8. Pick a Qwen model that supports tool calling; check Ollama library for current tags. |
| SQLite | Demo app database (inside the `db` service) | stdlib `sqlite3` |
| vis-network or Cytoscape.js | Graph rendering in the UI | CDN script |

## 4. Architecture

```
 browser ──► frontend ──► checkout ──► db(SQLite)        <- demo "shop" system
 loadgen ──►    │            │           │
                └── /metrics ┴───────────┘
                         │
                    Prometheus <────────────┐
 container stdout ─► Alloy ─► Loki <────────┤
 docker.sock (ro) ──────────────────────────┤
 deploys.json (ro) ─────────────────────────┤
                                       investigator (FastAPI)
                                        adapters -> collect/summarize
                                        graph + timeline + pre-ranker
                                        agent (LLM tool loop)  ──► Ollama (host)
                                        API + SSE + static UI
```

### Naming rule (critical)
For each service `X` the following must be **identical**: compose service name, `container_name`, Prometheus `job_name`, Loki label `service`, key in `services.yaml`. Everything filters by this one name.

### Ports (host)
| Port | Service |
|---|---|
| 8000 | investigator (API + UI) |
| 8001 | frontend (demo shop) |
| 8002 | checkout |
| 8003 | db service |
| 9090 | Prometheus |
| 3100 | Loki |
| 12345 | Alloy UI (debug) |
| 8080 | cAdvisor (optional) |
| 3000 | Grafana (optional) |
| 11434 | Ollama (on host) |

### Time units (most common bug)
Prometheus: epoch **seconds**. Loki: epoch **nanoseconds** (as string/int). Docker SDK `logs(since, until)`: epoch **seconds** (int). Jaeger (later): **microseconds**. Put all conversions in one `timeutil.py`.

### Repo layout
```
AGENTS.md
docker-compose.yml
.env.example
.gitignore
data/deploys.json            # change events written by fault scripts, read-only for investigator
prometheus/prometheus.yml
loki/                        # config if the image default is not enough
alloy/config.alloy
demo/
  frontend/  (Dockerfile, app.py, static/index.html, static/app.js, static/style.css)
  checkout/  (Dockerfile, app.py)
  db/        (Dockerfile, app.py)
  common/    (shared observability helper copied into each image, see Stage 4)
  loadgen/   (Dockerfile, loadgen.py)
scripts/inject_fault.py      # one CLI for all faults, also records deploy events
investigator/
  Dockerfile, requirements.txt, requirements-dev.txt, pytest.ini, services.yaml
  app/ main.py config.py timeutil.py summarize.py collect.py graph.py timeline.py
       adapters/ prometheus.py loki.py dockerlogs.py
       agent/ llm.py tools.py loop.py prompts/*.md
  tests/ fixtures/
  eval/ faults.yaml run_eval.py
```

## 5. The demo app ("ShopLite")

Purpose: a **small, simple** system that is easy to break and produces realistic, **fake** incidents. It is a victim, not a product. No auth, no payments, no real data.

Behaviour: a page lists 4-6 products. User clicks Buy. `frontend` calls `checkout`, which asks `db` to check stock and write an order. `loadgen` sends steady traffic so metrics always exist.

Services:
- **frontend**: serves the static page, proxies `/api/*` to checkout, and (Stage 4) proxies `/admin/fault/{service}/{kind}` to the other services.
- **checkout**: `GET /products`, `POST /checkout {product_id, qty}`. Calls `db`.
- **db**: SQLite behind HTTP: `GET /products`, `GET /products/{id}`, `POST /orders`. Has a small simulated **connection pool** (a semaphore, default 5 slots, each query holds a slot ~20 ms) so "pool exhausted" is a real failure mode.

### Build the demo app slowly, in this order (Stages 1 to 4)
1. **Frontend boilerplate only**: static HTML/CSS page, hardcoded products, no JavaScript logic, no backend.
2. **Interactivity next**: JS cart, Buy button, fake "order placed" result from **mock data in JS**, a fault panel whose buttons only toggle UI state. Still no backend.
3. **Working backend then**: add `db` and `checkout`, make the frontend call them for real, remove the JS mocks.
4. **Then observability and faults**: metrics, logging format, fault endpoints, loadgen.

Do not write the next layer until the previous layer's Gate passes.

### Fault catalog (this is also the evaluation ground truth)
All faults are triggered by `scripts/inject_fault.py <fault_id>` (and `reset`). Each also appends an event to `data/deploys.json` when it represents a change.

| fault_id | How it is triggered | What you should see | Expected root cause |
|---|---|---|---|
| `db_latency` | `POST db:/fault/latency?ms=800` | db p95 up, checkout p95 up, frontend p95 up | db slow |
| `db_errors` | `POST db:/fault/errors?rate=0.6` | db 5xx, checkout 5xx/502, frontend 502; log: `injected fault` | db returning errors |
| `db_pool_exhausted` | `POST db:/fault/pool?hold_seconds=60` (grabs all slots) | db 503, log: `connection pool exhausted` | db connection pool exhaustion |
| `checkout_memory_leak` | `POST checkout:/fault/leak?mb_per_request=1` plus compose `mem_limit: 128m` on checkout | memory climbs, container OOMKilled, restart count rises, brief 502s | checkout memory leak |
| `checkout_crash` | `docker stop checkout` | frontend 502, log: `downstream call failed: ConnectError`; checkout metrics stop | checkout down |
| `bad_deploy` | `POST checkout:/fault/errors?rate=0.4` **and** deploy event `{time, service: checkout, version: v2, change: "payment_timeout_ms 2000 -> 50"}` appended to `deploys.json` | checkout 5xx starting at deploy time | bad deploy of checkout |

## 6. Stages (pipeline to pipeline)

### Stage 0: scaffold
Build: git repo, `.gitignore`, folder layout from Section 4, empty compose file, `.env.example`, root `README.md` (short).
Gate: `docker compose config` succeeds; repo tree matches layout.
Commit: `chore: repo scaffold`

### Stage 1: demo frontend boilerplate
Build: `demo/frontend` with a Dockerfile, FastAPI app serving `static/` and `GET /health`. `index.html` + CSS: header, product grid (hardcoded 4-6 products), empty cart area, footer. **No JS logic, no fetch.** Compose service `frontend` on 8001.
Gate: `docker compose up --build -d frontend`; open `http://localhost:8001` and see the page; `curl localhost:8001/health` returns `{"status":"ok"}`.
Commit: `feat(demo): frontend boilerplate`

### Stage 2: demo frontend interactivity (still no backend)
Build: `app.js` with in-memory cart, add/remove, total, a Buy button that shows a fake "order placed" message after a short delay, a "Fault panel" (collapsed section) with buttons whose only effect is updating on-page status text. Data comes from a JS array.
Gate: in the browser: add items, totals change, Buy shows the confirmation, fault buttons update status text. No network calls in the browser devtools Network tab other than static files.
Commit: `feat(demo): frontend interactivity with mock data`

### Stage 3: demo backend (checkout + db), wired for real
Build:
1. `db` service: SQLite file created at startup with a `products` table (seed 5 rows) and `orders` table. Endpoints from Section 5. Pool semaphore (size 5) wrapped around each query. Log lines as `LEVEL message` (Section 7).
2. `checkout` service: `GET /products` (proxy to db), `POST /checkout` (check stock via db, create order via db, return order id). Downstream failures become `502` plus an ERROR log line. Use one shared `httpx.AsyncClient(timeout=3.0)`.
3. `frontend`: add `/api/products` and `/api/checkout` proxy routes to checkout; switch `app.js` from mock data to `fetch`. Remove mocks.
4. Compose: services `db`, `checkout`, `frontend` with `depends_on`, `container_name` equal to service name.
Gate: browser shows products loaded from the db; Buy creates an order (`curl localhost:8003/orders` lists it); `docker compose stop db` then Buy shows an error in the UI and an ERROR line appears in `docker compose logs checkout`.
Commit: `feat(demo): checkout and db backend`

### Stage 4: observability hooks + fault injection + loadgen
Build:
1. `demo/common/observability.py` (shared by all three images: set the compose build `context: ./demo` and `dockerfile: <service>/Dockerfile`, then `COPY common/ ./common/` in each Dockerfile): the metrics middleware and `/metrics` route from Section 9.1. Exclude `/metrics`, `/health`, `/docs`, `/openapi.json` from tracking.
2. Fault state + `/fault/*` endpoints per Section 5 on db and checkout (`latency`, `errors`, `pool`, `leak`, `reset`). Each fault logs a WARNING line when set.
3. `frontend` `/admin/fault/{service}/{kind}` proxy (whitelist service names and kinds); wire the fault panel buttons to it.
4. `demo/loadgen`: loop calling `POST frontend:/api/checkout` every ~0.2 s, swallowing errors.
5. `scripts/inject_fault.py` implementing every `fault_id` in the catalog plus `reset`; it appends to `data/deploys.json` for `bad_deploy`.
6. `mem_limit: 128m` on checkout in compose; `logging` rotation anchor (json-file, `max-size: 10m`, `max-file: 3`) on every service.
Gate: `curl localhost:8002/metrics` shows `http_requests_total` and `http_request_duration_seconds_bucket` increasing while loadgen runs; `python scripts/inject_fault.py db_errors` makes `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8001/api/checkout ...` return 502 sometimes; `reset` restores 200s.
Commit: `feat(demo): metrics, faults, loadgen`

### Stage 5: Prometheus (the first telemetry pipeline, metrics half)
Build: `prometheus/prometheus.yml` (Section 9.2), compose service `prometheus` with `--storage.tsdb.retention.time=6h`, port 9090. Optional: cAdvisor service **[UNVERIFIED]** plus a scrape job for it.
Gate:
1. `http://localhost:9090/targets` shows frontend, checkout, db all **UP**.
2. Prometheus UI query `sum(rate(http_requests_total[1m])) by (job)` returns 3 series.
3. Run `db_latency`, wait **60 seconds**, then query `histogram_quantile(0.95, sum by (le,job) (rate(http_request_duration_seconds_bucket[1m])))`: db, checkout and frontend p95 all rise toward ~0.8 s.
4. `reset`, wait 60 s, values return to normal.
**If you cannot see the fault in a Prometheus graph, the investigator will not see it either. Do not continue until you can.**
Commit: `feat(infra): prometheus scraping`

### Stage 6: Loki + Alloy (logs half) **[UNVERIFIED, verify against current Loki/Alloy docs]**
Build: compose services `loki` (port 3100, use the image's default local config at first) and `alloy` (mounts `alloy/config.alloy` and `/var/run/docker.sock:ro`). Use the config in Section 9.3 as a starting draft; fix syntax against the current Alloy docs if it errors. Every log line must end up with the label `service="<container name>"`.
Gate:
1. `curl localhost:3100/ready` returns `ready` (can take ~15 s after start).
2. Alloy UI `http://localhost:12345` shows the components healthy.
3. `curl -G "http://localhost:3100/loki/api/v1/query_range" --data-urlencode 'query={service="checkout"} |= "ERROR"' --data-urlencode "limit=5"` returns streams with ERROR lines after you run `db_errors`.
4. `curl -G localhost:3100/loki/api/v1/label/service/values` lists frontend, checkout, db.
If Alloy cannot be made to work in reasonable time, **stop and tell the human**; the Docker SDK fallback adapter (Stage 7) keeps the project moving.
Commit: `feat(infra): loki and alloy log pipeline`

### Stage 7: investigator data path (no LLM)
Build, in this order, testing each piece before the next:
1. `config.py` (pydantic-settings: `PROMETHEUS_URL`, `LOKI_URL`, `SERVICES_FILE`, caps), `services.yaml` (Section 9.4), `timeutil.py`.
2. `summarize.py::summarize_series` (Section 9.5) + unit tests.
3. `adapters/prometheus.py::query_range` (Section 9.6).
4. Log parsing/dedup pure function (Section 9.7) + unit tests, then `adapters/loki.py::get_error_logs` (query `{service="X"} |~ "ERROR|CRITICAL"`, window in **nanoseconds**, limit 500, then dedupe). Then `adapters/dockerlogs.py` as the fallback with the same return shape.
5. `collect.py`: `collect_metrics`, `collect_logs`. Logs try Loki first and fall back to Docker SDK; any failure becomes `{"error": "..."}` in that section, never an exception.
6. `main.py`: `GET /health`, `GET /services`, `POST /investigations {service, window_minutes}` (validate `service` against `services.yaml` **before** it is placed in a PromQL/LogQL string; 404 otherwise). Plain `def` endpoints (not `async`) because the adapters are blocking.
7. Compose service `investigator` with env URLs and the docker socket mounted read-only.
Gate:
1. `cd investigator && pytest` all green (no Docker needed).
2. Healthy: `POST /investigations {"service":"checkout","window_minutes":5}` returns flat metrics, `error_ratio ~ 0`, no error patterns.
3. Run `db_errors`, wait 60 s, investigate `checkout` and `db`: `error_ratio` max well above 0.3 with a `jump_at` timestamp, and `logs.patterns` contains something like `downstream returned status N` (checkout) and `injected fault: internal error...` (db).
4. Repeat for `db_latency`: `latency_p95_seconds.max` near 0.8-1.0.
5. Stop Loki (`docker compose stop loki`): response still returns metrics, and logs come from the Docker fallback or a clean `{"error": ...}`.
6. `service: "nope"` returns 404.
Commit: `feat(investigator): metrics and logs collection endpoint`

**Stages 0 to 7 are "the first pipeline". Stop here and report to the human before continuing.**

### Stage 8 onward (build only when asked, one at a time)
8. **Graph + pre-ranker + timeline.** `graph.py` loads `services.yaml` into a `networkx.DiGraph` behind `get_downstream/get_upstream/mark_health`. Health from Stage 7 metrics (unhealthy if `error_ratio > 0.05` or p95 > 3x baseline and > 0.3 s). **Pre-rank:** candidates are unhealthy services none of whose dependencies are unhealthy (plus services whose container is down). `timeline.py` merges metric jump times, log pattern first-seen times, container restarts/OOMKills (Docker API) and `deploys.json` events into one sorted list. Add `graph` and `timeline` and `candidates` to the `/investigations` response. Tests use fixtures, not live services.
9. **Fixtures + eval set.** `eval/faults.yaml` (the Section 5 catalog with expected root cause). A script dumps the collected evidence for each fault to `tests/fixtures/<fault_id>.json` so the agent and UI can be developed without the stack running.
10. **LLM + agent.** `agent/llm.py` (OpenAI-compatible client, `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY` from env; default `http://host.docker.internal:11434/v1`, on Linux add `extra_hosts: host.docker.internal:host-gateway`). Ollama's default context is small and the OpenAI-compatible API cannot set it per request, so set a context of at least 8192 via a Modelfile (`PARAMETER num_ctx`) or Ollama's context-length env var (verify in Ollama docs). Build in sub-steps, committing each: (a) one LLM call, context in, JSON hypotheses out, no tools; (b) tool loop with `query_prometheus`, `search_logs`, `get_container_status`, `get_downstream`, `get_incident_history`, max 6 steps, temperature 0-0.2; (c) tool whitelist + argument validation; (d) strict output schema validated with Pydantic, every root cause must have an `evidence` list, retry once on parse failure; (e) every step emitted as an event and saved. Tools are plain Python functions, **read-only**, results truncated (top 10 deduped log patterns, summarized metrics). Tool errors go back to the LLM as text. Small local models are weaker: let the pre-ranker give 2-3 candidates and have the LLM validate them. Prompts live in `agent/prompts/*.md`.
11. **API lifecycle + SSE + UI.** `POST /investigations` returns `{id}` immediately, runs the agent as a background task, `GET /investigations/{id}/stream` (SSE via `sse-starlette`) pushes step events, `GET /investigations/{id}` returns the final report. Store in a dict, persist to JSON. UI: select service/fault, live step log, timeline list, dependency graph colored by health (green/orange/red), ranked causes with expandable evidence. Show the active model name in the UI.
12. **Eval loop.** Run every fault 3-5 times; record top-1 correct and seconds. Compare at least two models. Fix prompts/tools/truncation from failures.
13. **Stretch (only if everything above is solid):** OTel tracing to Jaeger to build the graph from spans (replaces `services.yaml`; keep the same graph interface), incident records + `get_incident_history`, Neo4j implementation of the graph interface, Kubernetes adapter, VS Code extension wrapper (webview calling the same API).

## 7. Conventions

- Log format in every demo service: `LEVEL message` on stdout with `PYTHONUNBUFFERED=1`. Docker/Alloy add the timestamp. Do not add timestamps in the app line.
- Environment-driven config only. Provide `.env.example`.
- Investigator tools never accept free-form shell or arbitrary URLs. Arguments are validated against known service names and capped windows (max 120 minutes).
- Never put user IDs or request IDs into metric labels (cardinality).
- Commit once per stage, message given in the stage.
- Tests: pure functions get unit tests; live-stack checks are the Gates, not pytest.

## 8. Testing and debugging playbook (what worked)

**[VERIFIED] in a sandbox:** the demo-app metrics middleware, three services chained with fault propagation, a real Prometheus v2.55.1 scraping them, the PromQL queries below, `summarize_series`, the log dedup parser, the investigator endpoint, and graceful degradation when Docker is unavailable. **Not run:** Docker log reading, Loki, Alloy, cAdvisor, anything LLM.

How to test:
1. **Look at the data before coding against it.** Open the Prometheus UI, find the real metric names/labels, test the PromQL there, then paste into code.
2. **Prove the fault is visible** in a Prometheus graph before touching the investigator.
3. **Wait for rate windows.** Scrape interval is 5 s and queries use `[1m]`. After injecting or resetting a fault, wait **~45-60 s** before judging results. Early "no change" is usually just timing.
4. **Baseline first**, then fault, then reset. Always compare against a healthy run.
5. **Unit-test pure functions** (summarize, log parsing) with synthetic data; run them without Docker.
6. **Failure must degrade, not crash.** Adapters raise typed errors; `collect.py` converts them into `{"error": "..."}` so the agent (later) sees "tool failed: timeout" instead of a stack trace. Test by stopping Prometheus/Loki.
7. **Shell gotcha in agent sandboxes:** background servers started in one tool call may be killed when the call ends. Start them with `setsid nohup ... &` and run the test commands in the **same** call, or use `docker compose up -d`.

Known problems and fixes:
| Symptom | Cause / fix |
|---|---|
| `error_ratio` returns empty or NaN | No 5xx series exists yet, or zero traffic. Use `(sum(rate(...5xx...)) or vector(0)) / sum(rate(...))`; `summarize_series` skips NaN/Inf. |
| Prometheus `/metrics` scrape redirects | Do not `mount()` the metrics ASGI app at `/metrics`; use a normal `@app.get("/metrics")` route returning `generate_latest()`. |
| Logs empty in container logs | Missing `PYTHONUNBUFFERED=1`. |
| `connection refused` between containers | Using `localhost` inside a container. Use the service name (`http://db:8000`). Check `depends_on` and startup order; retry in loadgen. |
| Metrics show nothing for a service | `job_name` does not match the service name used in the query. |
| Exceptions with empty message in logs | `str(e)` can be empty (timeouts). Log `type(e).__name__` too. |
| Port already in use | Change the left side of the `ports:` mapping. |
| Docker logs adapter fails on Windows | Needs Docker Desktop socket access; fall back to Loki. |
| Loki says `too many outstanding requests` / not ready | Wait ~15-30 s after start; check `/ready`. |
| Rates look odd right after startup | Ramp-up noise in the first minute; ignore the first window. |
| Docker log timestamps | `logs(timestamps=True)` prefixes `2026-10-12T13:51:30.123456789Z `; Loki path has no such prefix. Parser handles both by making the timestamp optional. |

## 9. Reference implementations **[VERIFIED unless marked]**

### 9.1 Demo app observability (metrics middleware + faults skeleton)
```python
import asyncio, logging, os, random, time
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = os.getenv("SERVICE_NAME", "service")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(SERVICE)
app = FastAPI(title=f"demo:{SERVICE}")

faults = {"latency_ms": 0, "error_rate": 0.0}

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP latency", ["method", "path"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
UNTRACKED = {"/metrics", "/health", "/docs", "/openapi.json"}

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

# inside a request handler:
#   if faults["latency_ms"]: await asyncio.sleep(faults["latency_ms"] / 1000)
#   if random.random() < faults["error_rate"]:
#       log.error("injected fault: internal error while handling request"); raise HTTPException(500)
# downstream failure handling:
#   except Exception as e: log.error("downstream call failed: %s %s", type(e).__name__, e); raise HTTPException(502)
#   if r.status_code >= 500: log.error("downstream returned status %s", r.status_code); raise HTTPException(502)
```

### 9.2 `prometheus/prometheus.yml`
```yaml
global:
  scrape_interval: 5s
scrape_configs:
  - job_name: frontend
    static_configs: [{targets: ["frontend:8000"]}]
  - job_name: checkout
    static_configs: [{targets: ["checkout:8000"]}]
  - job_name: db
    static_configs: [{targets: ["db:8000"]}]
```
Compose: mount it read-only at `/etc/prometheus/prometheus.yml`; command flags `--config.file=/etc/prometheus/prometheus.yml --storage.tsdb.retention.time=6h`.

### 9.3 `alloy/config.alloy` **[UNVERIFIED draft, check current Alloy docs]**
```
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

discovery.relabel "containers" {
  targets = []
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(.*)"
    target_label  = "service"
  }
}

loki.source.docker "containers" {
  host          = "unix:///var/run/docker.sock"
  targets       = discovery.docker.containers.targets
  relabel_rules = discovery.relabel.containers.rules
  forward_to    = [loki.write.local.receiver]
}

loki.write "local" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```
Only ship our demo containers if the label set gets noisy (filter on container name regex).

### 9.4 `investigator/services.yaml` (hand-written dependency graph, replaced by traces in Stage 13)
```yaml
services:
  frontend: {container: frontend, depends_on: [checkout]}
  checkout: {container: checkout, depends_on: [db]}
  db:       {container: db,       depends_on: []}
```

### 9.5 Metric queries and summarizer
`__SVC__` is replaced with a service name that was **validated against `services.yaml`**.
```python
METRICS = {
  "request_rate_per_s": {"min_delta": 0.5,
    "query": 'sum(rate(http_requests_total{job="__SVC__"}[1m]))'},
  "error_ratio": {"min_delta": 0.05,
    "query": '(sum(rate(http_requests_total{job="__SVC__",status=~"5.."}[1m])) or vector(0))'
             ' / sum(rate(http_requests_total{job="__SVC__"}[1m]))'},
  "latency_p95_seconds": {"min_delta": 0.1,
    "query": 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="__SVC__"}[1m])))'},
}
```
```python
import math
from datetime import datetime, timezone

def iso(ts): return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")

def summarize_series(values, min_delta=0.0, jump_factor=2.0):
    pts = []
    for ts, raw in values:
        try: v = float(raw)
        except (TypeError, ValueError): continue
        if math.isnan(v) or math.isinf(v): continue
        pts.append((float(ts), v))
    if not pts: return None
    nums = [v for _, v in pts]
    n_base = max(1, len(pts) // 4)
    baseline = sum(nums[:n_base]) / n_base
    peak_ts, peak = max(pts, key=lambda p: p[1])
    jump_at = next((iso(ts) for ts, v in pts[n_base:]
                    if v - baseline > min_delta and v > baseline * jump_factor), None)
    return {"baseline": round(baseline, 4), "min": round(min(nums), 4), "max": round(peak, 4),
            "avg": round(sum(nums) / len(nums), 4), "last": round(nums[-1], 4),
            "peak_at": iso(peak_ts), "jump_at": jump_at, "points": len(pts)}
```
Unit tests to include: flat series has `jump_at is None`; NaN-only returns `None`; step from 0.05 to 0.9 yields a `jump_at` and `max == 0.9`.

### 9.6 Prometheus adapter
```python
import httpx
class PrometheusError(Exception): ...

def query_range(query, start, end, step="15s"):
    try:
        r = httpx.get(f"{settings.prometheus_url}/api/v1/query_range",
                      params={"query": query, "start": start, "end": end, "step": step}, timeout=10.0)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise PrometheusError(f"Prometheus request failed: {type(e).__name__}: {e}") from e
    body = r.json()
    if body.get("status") != "success":
        raise PrometheusError(f"Prometheus error: {body.get('error', 'unknown')}")
    return body["data"]["result"]        # [] means no data, handle it
```

### 9.7 Log dedup (pure function, unit-testable)
```python
import re
from collections import OrderedDict
# Docker-SDK path lines have a leading timestamp token; Loki path lines do not. Make it optional.
LINE_RE = re.compile(r"^(?:(?P<ts>\d{4}-\S+)\s+)?(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<msg>.*)$")
BAD = {"ERROR", "CRITICAL"}

def pattern(msg): return re.sub(r"\d+", "N", msg)[:200]      # '142 timeouts' ~ '97 timeouts'

def summarize_log_text(text, max_patterns=10):
    scanned = errors = 0
    groups = OrderedDict()
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m: continue
        scanned += 1
        if m["level"] not in BAD: continue
        errors += 1
        key, ts = pattern(m["msg"]), (m["ts"] or "")[:19]
        g = groups.get(key)
        if g is None: groups[key] = {"count": 1, "pattern": key, "example": m["msg"][:200], "first_seen": ts, "last_seen": ts}
        else: g["count"] += 1; g["last_seen"] = ts or g["last_seen"]
    top = sorted(groups.values(), key=lambda g: g["count"], reverse=True)[:max_patterns]
    return {"lines_scanned": scanned, "error_lines": errors, "patterns": top}
```
For the Loki adapter, take the timestamp from the Loki entry (`[ts_ns, line]`) and fill `first_seen/last_seen` from it instead of parsing the line. Docker SDK fallback: `container.logs(since=int(start), until=int(end)+1, timestamps=True)`.

### 9.8 `/investigations` response shape (Stage 7)
```json
{
  "service": "checkout",
  "depends_on": ["db"],
  "window": {"start": "...Z", "end": "...Z", "minutes": 15},
  "metrics": {
    "request_rate_per_s": {"baseline": 1.0, "max": 3.4, "last": 1.3, "jump_at": null, "...": "..."},
    "error_ratio": {"baseline": 0.0, "max": 0.47, "jump_at": "...", "...": "..."},
    "latency_p95_seconds": {"baseline": 0.01, "max": 0.96, "jump_at": "...", "...": "..."}
  },
  "logs": {"source": "loki", "lines_scanned": 304, "error_lines": 40,
           "patterns": [{"count": 40, "pattern": "downstream returned status N", "first_seen": "...", "last_seen": "..."}]}
}
```
A section may instead be `{"error": "..."}` or `{"note": "no data in this window"}`.

## 10. Definition of done for the first pipeline (Stages 0-7)

- `docker compose up --build -d` brings up frontend, checkout, db, loadgen, prometheus, loki, alloy, investigator.
- All three Prometheus targets UP; Loki has `service` label values for all three.
- For `db_errors` and `db_latency`, the `/investigations` output for `checkout` and `db` clearly shows the fault (jump times, error patterns), and `reset` brings it back to normal.
- `pytest` passes without Docker.
- README explains how to run, verify, and inject faults, with Windows-safe commands.
- No LLM code exists yet.

Then stop and report to the human.
