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

mkdir -p "$PID_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found. Run:"
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH=.
export NO_PROXY='*'
export no_proxy='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy 2>/dev/null || true

if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "Starting FastAPI on http://localhost:8000 …"
  nohup .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000 \
    >"$API_LOG" 2>&1 &
  echo $! >"$API_PID_FILE"

  for _ in {1..45}; do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "FastAPI failed to start. Last log lines:"
    tail -20 "$API_LOG" || true
    exit 1
  fi
fi

if curl -sf http://127.0.0.1:8502/_stcore/health >/dev/null 2>&1; then
  echo "Customer portal already running."
  echo ""
  echo "  Portal: http://localhost:8502"
  echo "  API:    http://localhost:8000/health"
  exit 0
fi

# Stop stale portal process on port 8502 before starting fresh.
if [[ -f "$PORTAL_PID_FILE" ]]; then
  old_pid="$(cat "$PORTAL_PID_FILE")"
  kill "$old_pid" 2>/dev/null || true
fi

echo "Starting customer portal on http://localhost:8502 …"
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  nohup .venv/bin/streamlit run src/ui/customer_portal.py \
    --server.headless true \
    --server.port 8502 \
  >"$PORTAL_LOG" 2>&1 &
echo $! >"$PORTAL_PID_FILE"

for _ in {1..30}; do
  if curl -sf http://127.0.0.1:8502/_stcore/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf http://127.0.0.1:8502/_stcore/health >/dev/null 2>&1; then
  echo "Customer portal failed to start. Last log lines:"
  tail -20 "$PORTAL_LOG" || true
  exit 1
fi

echo ""
echo "=========================================="
echo "  Paytm Customer Portal is running"
echo "=========================================="
echo ""
echo "  Portal: http://localhost:8502"
echo "  API:    http://localhost:8000/health"
echo ""
echo "  Test login: henry010 / Pay@5649"
echo ""
echo "  Logs: .demo/customer_portal.log"
echo ""

if [[ "$(uname -s)" == "Darwin" ]]; then
  open "http://localhost:8502" 2>/dev/null || true
fi
