#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

echo "Starting Paytm Resolution Copilot Platform..."

# Activate venv
source .venv/bin/activate
export PYTHONPATH=.
export NO_PROXY='*'
export no_proxy='*'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy 2>/dev/null || true

# Start FastAPI
echo "Starting API on port 8000..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for API to be ready
sleep 3

# Start all four Streamlit portals
echo "Starting Landing Page on port 8500..."
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  streamlit run src/ui/landing.py --server.port 8500 \
  --server.headless true &

echo "Starting Agent Portal on port 8501..."
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  streamlit run src/ui/app.py --server.port 8501 \
  --server.headless true &

echo "Starting Customer Portal on port 8502..."
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  streamlit run src/ui/customer_portal.py --server.port 8502 \
  --server.headless true &

echo "Starting Merchant Portal on port 8503..."
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
  streamlit run src/ui/merchant_portal.py --server.port 8503 \
  --server.headless true &

echo ""
echo "Platform is running:"
echo "  Landing Page  → http://localhost:8500"
echo "  Agent Portal  → http://localhost:8501"
echo "  Customer      → http://localhost:8502"
echo "  Merchant      → http://localhost:8503"
echo "  API docs      → http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services."

# Keep running, kill all children on exit
trap "kill 0" EXIT
wait
