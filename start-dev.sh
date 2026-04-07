#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Shutting down..."
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null
  wait 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "ERROR: backend/.venv not found. Run:  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [ ! -f "$ROOT/backend/.env" ]; then
  echo "WARNING: backend/.env missing — copy backend/.env.example and fill in your keys."
fi

echo "==> Starting backend (uvicorn :8000) ..."
cd "$ROOT/backend"
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

sleep 2
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo "ERROR: Backend failed to start."
  exit 1
fi

echo "==> Starting frontend (vite :8080) ..."
cd "$ROOT"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:8080"
echo "  Press Ctrl+C to stop both."
echo ""

wait
