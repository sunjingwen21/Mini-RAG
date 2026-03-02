#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/log/minirag.pid"

echo "=================================================="
echo "Stopping Mini-RAG"
echo "=================================================="

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Mini-RAG stopped (PID: $PID)."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if command -v pkill >/dev/null 2>&1 && pkill -f "python.*run.py|uvicorn"; then
  echo "Mini-RAG stopped."
  exit 0
fi

echo "No running Mini-RAG process was found."
