#!/usr/bin/env bash
# Start FastAPI + Streamlit in the background (survives closing the task terminal).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PID_DIR="$ROOT_DIR/.demo"
API_PID_FILE="$PID_DIR/api.pid"
UI_PID_FILE="$PID_DIR/streamlit.pid"
API_LOG="$PID_DIR/api.log"
UI_LOG="$PID_DIR/streamlit.log"

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

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  kill -0 "$pid" 2>/dev/null
}

if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 \
   && curl -sf http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
  echo "Demo already running."
  echo ""
  echo "  UI:  http://localhost:8501"
  echo "  API: http://localhost:8000/health"
  exit 0
fi

# Stop stale processes on our ports before starting fresh.
"$ROOT_DIR/scripts/stop_demo.sh" >/dev/null 2>&1 || true

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

echo "FastAPI is ready."
echo "Starting Streamlit on http://localhost:8501 …"
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  nohup .venv/bin/streamlit run src/ui/app.py \
    --server.headless true \
    --server.port 8501 \
  >"$UI_LOG" 2>&1 &
echo $! >"$UI_PID_FILE"

for _ in {1..30}; do
  if curl -sf http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
  echo "Streamlit failed to start. Last log lines:"
  tail -20 "$UI_LOG" || true
  exit 1
fi

echo ""
echo "=========================================="
echo "  Paytm Resolution Copilot is running"
echo "=========================================="
echo ""
echo "  UI:  http://localhost:8501"
echo "  API: http://localhost:8000/health"
echo ""
echo "  Logs: .demo/api.log  .demo/streamlit.log"
echo "  Stop: ./scripts/stop_demo.sh"
echo "        or Cursor task \"Paytm: Stop Demo\""
echo ""

if [[ "$(uname -s)" == "Darwin" ]]; then
  open "http://localhost:8501" 2>/dev/null || true
fi
