#!/usr/bin/env bash
# Stop background FastAPI and Streamlit demo servers.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT_DIR/.demo"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $label (pid $pid)…"
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_pid_file "FastAPI" "$PID_DIR/api.pid"
stop_pid_file "Streamlit" "$PID_DIR/streamlit.pid"

# Fallback: free ports if something else is bound.
for port in 8000 8501; do
  if lsof -ti:"$port" >/dev/null 2>&1; then
    echo "Freeing port $port …"
    lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
  fi
done

echo "Demo servers stopped."
