#!/usr/bin/env bash
# =================================================================
# RootTrace · Autonomous Incident Investigator Initializer (POSIX)
# =================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo ""
echo "================================================================="
echo "   ROOT-TRACE · Autonomous Incident Investigator Initializer    "
echo "================================================================="
echo "Project Root: $PROJECT_ROOT"
echo ""

# 1. Environment & Data Files
echo "[1/4] Checking environment configuration..."
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "  -> Created .env from .env.example"
  fi
else
  echo "  -> .env file is present"
fi

mkdir -p data
if [ ! -f data/deploys.json ]; then
  echo "[]" > data/deploys.json
  echo "  -> Initialized data/deploys.json"
fi

# 2. Docker Daemon Verification
echo ""
echo "[2/4] Verifying Docker daemon..."
if ! docker info >/dev/null 2>&1; then
  echo "  -> Error: Docker is not running. Please start Docker / Docker Desktop and re-run."
  exit 1
fi
echo "  -> Docker daemon is responsive"

# 3. Docker Compose Services
echo ""
echo "[3/4] Starting microservices via Docker Compose..."
if [ "$1" == "--build" ] || [ "$1" == "-b" ]; then
  docker compose up -d --build
else
  docker compose up -d
fi

# 4. Service Health Checks
echo ""
echo "[4/4] Verifying service endpoints..."
sleep 4

check_endpoint() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000")
  if [ "$code" -eq 200 ]; then
    echo "  -> [OK] $name (HTTP $code)"
  else
    echo "  -> [WAIT/WARN] $name (HTTP $code - $url)"
  fi
}

check_endpoint "Investigator (API & UI)" "http://localhost:8000/health"
check_endpoint "ShopLite Demo Frontend"   "http://localhost:8001/health"
check_endpoint "Checkout Microservice"    "http://localhost:8002/health"
check_endpoint "Database Service"         "http://localhost:8003/health"
check_endpoint "Prometheus TSDB"          "http://localhost:9090/-/healthy"
check_endpoint "Grafana Loki"             "http://localhost:3100/ready"

echo ""
echo "================================================================="
echo "   ROOT-TRACE STACK IS UP AND READY!                            "
echo "================================================================="
echo ""
echo "  • Investigator Console (UI & API) : http://localhost:8000"
echo "  • ShopLite Demo Storefront        : http://localhost:8001"
echo "  • Prometheus Time-Series Metrics  : http://localhost:9090"
echo "  • Grafana Loki Logs Pipeline      : http://localhost:3100"
echo "  • Grafana Alloy Debug Interface   : http://localhost:12345"
echo ""
