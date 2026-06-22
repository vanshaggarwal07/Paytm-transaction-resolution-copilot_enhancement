#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH=.
# Avoid corporate proxy blocking Hugging Face model cache / Gemini API calls.
export NO_PROXY='*'
export no_proxy='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy 2>/dev/null || true

API_PID=""

cleanup() {
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
    echo ""
    echo "Stopping FastAPI (pid $API_PID)…"
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "Starting FastAPI on http://localhost:8000 …"
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

for _ in {1..30}; do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "FastAPI failed to start. Check logs above."
  exit 1
fi

echo "FastAPI is ready."
echo "Starting Streamlit on http://localhost:8501 …"
echo "Press Ctrl+C to stop both servers."
echo ""

STREAMLIT_BROWSER_GATHER_USAGE_STATS=false streamlit run src/ui/app.py --server.headless true --server.port 8501
