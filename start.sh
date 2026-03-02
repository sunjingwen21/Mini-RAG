#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BASE_PYTHON="${PYTHON_BIN:-python3}"

if [[ ! -x "venv/bin/python" ]]; then
  echo "Creating virtual environment..."
  "$BASE_PYTHON" -m venv venv
fi

PYTHON_BIN="venv/bin/python"
PIP_BIN="venv/bin/pip"

if ! "$PYTHON_BIN" -c "import uvicorn, dotenv" >/dev/null 2>&1; then
  echo "Installing dependencies..."
  "$PIP_BIN" install --upgrade pip
  "$PIP_BIN" install -r requirements.txt
fi

if [[ -z "${MINI_RAG_ADMIN_TOKEN:-}" ]]; then
  echo "ERROR: MINI_RAG_ADMIN_TOKEN is required."
  echo "Set it in the environment or add it to a local .env file."
  exit 1
fi

echo "=================================================="
echo "Starting Mini-RAG"
echo "=================================================="
echo

exec "$PYTHON_BIN" run.py
