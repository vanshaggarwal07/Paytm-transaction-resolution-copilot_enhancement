#!/usr/bin/env bash
# Stop the customer portal on port 8502.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.demo/customer_portal.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  lsof -ti :8502 | xargs kill -9 2>/dev/null || true
fi

echo "Customer portal stopped."
