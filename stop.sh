#!/usr/bin/env bash
set -euo pipefail

echo "=================================================="
echo "Stopping Mini-RAG"
echo "=================================================="

if ! command -v pkill >/dev/null 2>&1; then
  echo "pkill is not available on this system."
  exit 1
fi

if pkill -f "python.*run.py|uvicorn"; then
  echo "Mini-RAG stopped."
  exit 0
fi

echo "No running Mini-RAG process was found."
