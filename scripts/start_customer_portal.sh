#!/usr/bin/env bash
# Start FastAPI (if needed) and the customer portal on port 8502.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PID_DIR="$ROOT_DIR/.demo"
API_PID_FILE="$PID_DIR/api.pid"
PORTAL_PID_FILE="$PID_DIR/customer_portal.pid"
API_LOG="$PID_DIR/api.log"
PORTAL_LOG="$PID_DIR/customer_portal.log"
PORTAL_URL="http://127.0.0.1:8502"

mkdir -p "$PID_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found. Run:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT_DIR"
export NO_PROXY='*'
export no_proxy='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy 2>/dev/null || true

portal_healthy() {
  curl -sf "$PORTAL_URL/_stcore/health" >/dev/null 2>&1
}

api_healthy() {
  curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1
}

if ! api_healthy; then
  echo "Starting FastAPI on http://127.0.0.1:8000 …"
  nohup .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000 \
    >"$API_LOG" 2>&1 &
  echo $! >"$API_PID_FILE"

  for _ in {1..45}; do
    if api_healthy; then
      break
    fi
    sleep 1
  done

  if ! api_healthy; then
    echo "FastAPI failed to start. Last log lines:"
    tail -30 "$API_LOG" || true
    exit 1
  fi
fi

if portal_healthy; then
  echo "Customer portal already running at $PORTAL_URL"
else
  "$ROOT_DIR/scripts/stop_customer_portal.sh" >/dev/null 2>&1 || true

  echo "Starting customer portal on $PORTAL_URL …"
  STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    nohup .venv/bin/streamlit run "$ROOT_DIR/src/ui/customer_portal.py" \
      --server.headless true \
      --server.address 127.0.0.1 \
      --server.port 8502 \
      --browser.serverAddress localhost \
      --browser.gatherUsageStats false \
    >"$PORTAL_LOG" 2>&1 &
  echo $! >"$PORTAL_PID_FILE"

  for _ in {1..45}; do
    if portal_healthy; then
      break
    fi
    sleep 1
  done

  if ! portal_healthy; then
    echo "Customer portal failed to start. Last log lines:"
    tail -30 "$PORTAL_LOG" || true
    exit 1
  fi
fi

echo ""
echo "=========================================="
echo "  Paytm Customer Portal is running"
echo "=========================================="
echo ""
echo "  Portal: $PORTAL_URL"
echo "  API:    http://127.0.0.1:8000/health"
echo ""
echo "  Test login:"
echo "    Username: henry010"
echo "    Password: Pay@5649"
echo ""
echo "  Logs: .demo/customer_portal.log"
echo "  Stop: ./scripts/stop_customer_portal.sh"
echo ""

if [[ "$(uname -s)" == "Darwin" ]]; then
  open "$PORTAL_URL" 2>/dev/null || true
fi
