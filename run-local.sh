#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/gan/Projects/AFS"
CONNECTOR_DIR="/home/gan/Projects/sheets-connector"
LOG_DIR="$APP_DIR/.local-logs"
PID_FILE="$LOG_DIR/afs-api.pid"
mkdir -p "$LOG_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found"
  exit 1
fi

start_afs_server() {
  nohup python3 "$APP_DIR/database/app_server.py" > "$LOG_DIR/afs-http.log" 2>&1 &
  afs_server_pid=$!
  printf '%s\n' "$afs_server_pid" > "$PID_FILE"
  echo "Starting AFS app and database API on http://localhost:8000"
}

afs_health=$(curl -fsS http://localhost:8000/api/health 2>/dev/null || true)
if [[ "$afs_health" == *'"api_version": 3'* ]]; then
  echo "AFS app and database API already running at http://localhost:8000"
elif [ -n "$afs_health" ]; then
  echo "AFS API lama masih berjalan. Restart server diperlukan."
  if [ -f "$PID_FILE" ]; then
    afs_old_pid=$(tr -cd '0-9' < "$PID_FILE")
    if [ -n "$afs_old_pid" ] && kill -0 "$afs_old_pid" 2>/dev/null; then
      kill "$afs_old_pid"
      for _ in 1 2 3 4 5; do
        if ! kill -0 "$afs_old_pid" 2>/dev/null; then break; fi
        sleep 1
      done
      start_afs_server
    else
      echo "PID server lama tidak aktif. Stop proses pada port 8000, lalu jalankan script ini lagi."
    fi
  else
    echo "PID server lama tidak ditemukan. Stop proses pada port 8000, lalu jalankan script ini lagi."
  fi
elif curl -fsS http://localhost:8000 >/dev/null 2>&1; then
  echo "Port 8000 is running the old static server. Stop it, then run this script again to enable the database API."
else
  start_afs_server
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
  if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
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
echo "Creator input: http://localhost:8000/apps/creator-entry.html"
echo "Creator tracker: http://localhost:8000/apps/creator-tracker.html"
echo "Connector: http://localhost:8765/append"
echo "Logs: $LOG_DIR"
