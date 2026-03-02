#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BASE_PYTHON="${PYTHON_BIN:-python3}"

if [[ ! -x "venv/bin/python" ]]; then
  echo "Creating virtual environment..."
  "$BASE_PYTHON" -m venv venv
fi

PYTHON_BIN="venv/bin/python"
PIP_BIN="venv/bin/pip"

if ! "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1; then
  echo "Installing dependencies..."
  "$PIP_BIN" install --upgrade pip
  "$PIP_BIN" install -r requirements.txt
fi

echo "=================================================="
echo "Starting Mini-RAG"
echo "=================================================="
echo

exec "$PYTHON_BIN" run.py
