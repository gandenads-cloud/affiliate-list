#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/gan/Projects/AFS"
CONNECTOR_DIR="/home/gan/Projects/sheets-connector"
LOG_DIR="$APP_DIR/.local-logs"
mkdir -p "$LOG_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found"
  exit 1
fi

if curl -fsS http://localhost:8000 >/dev/null 2>&1; then
  echo "AFS app already running at http://localhost:8000"
else
  nohup python3 -m http.server 8000 --directory "$APP_DIR" > "$LOG_DIR/afs-http.log" 2>&1 &
  echo "Starting AFS app on http://localhost:8000"
fi

if [ -f "$CONNECTOR_DIR/.venv/bin/activate" ]; then
  if curl -fsS http://localhost:8765/append >/dev/null 2>&1; then
    echo "Connector already running at http://localhost:8765/append"
  else
    nohup bash -lc 'source /home/gan/Projects/sheets-connector/.venv/bin/activate && cd /home/gan/Projects/sheets-connector && python server.py' > "$LOG_DIR/connector.log" 2>&1 &
    echo "Starting connector on http://localhost:8765/append"
  fi
else
  echo "Connector venv not found. Skip connector server."
fi

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://localhost:8000 >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://localhost:8765/append >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "AFS app: http://localhost:8000"
echo "Connector: http://localhost:8765/append"
echo "Logs: $LOG_DIR"
