#!/bin/bash
# Starts the Finora backend (port 8001) and frontend (port 5173). Stop with Ctrl+C.
cd "$(dirname "$0")"
trap 'kill 0' EXIT
(cd backend && source venv/bin/activate && uvicorn app.main:app --port 8001) &
(cd frontend && npm run dev) &
sleep 4
echo; echo "Finora is running:  http://localhost:5173     API docs: http://127.0.0.1:8001/docs"; echo
wait
