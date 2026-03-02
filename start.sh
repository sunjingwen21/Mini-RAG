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
LOG_DIR="$SCRIPT_DIR/log"
PID_FILE="$LOG_DIR/minirag.pid"
LAUNCHER_LOG="$LOG_DIR/launcher.log"

mkdir -p "$LOG_DIR"

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

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$EXISTING_PID" ]] && kill -0 "$EXISTING_PID" >/dev/null 2>&1; then
    echo "Mini-RAG is already running (PID: $EXISTING_PID)"
    echo "Logs: $LOG_DIR"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "=================================================="
echo "Starting Mini-RAG in background"
echo "=================================================="
echo "Logs directory: $LOG_DIR"

nohup "$PYTHON_BIN" run.py >> "$LAUNCHER_LOG" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

sleep 1
if ! kill -0 "$APP_PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "Mini-RAG failed to start. Check logs:"
  echo "  $LAUNCHER_LOG"
  exit 1
fi

echo "Mini-RAG started successfully."
echo "PID: $APP_PID"
echo "App log: $LOG_DIR/app.log"
echo "Access log: $LOG_DIR/access.log"
echo "Launcher log: $LAUNCHER_LOG"
