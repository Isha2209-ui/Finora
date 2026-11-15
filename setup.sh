#!/bin/bash
# One-time setup for Finora on macOS. Run from the project folder:  ./setup.sh
set -e
cd "$(dirname "$0")"
echo "== Backend: Python environment =="
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if [ ! -f .env ]; then
  if command -v createdb >/dev/null 2>&1 && createdb finora 2>/dev/null; then
    echo "Created PostgreSQL database 'finora'."
    cp .env.example .env
  elif command -v psql >/dev/null 2>&1 && psql -lqt 2>/dev/null | cut -d '|' -f 1 | grep -qw finora; then
    echo "PostgreSQL database 'finora' already exists."
    cp .env.example .env
  else
    echo "PostgreSQL not found - using the built-in SQLite fallback. (Install Postgres.app and re-run to switch.)"
    grep -v '^DATABASE_URL=' .env.example > .env
  fi
fi
echo "== Loading demo data =="
python -m app.data.seed
echo "== Checking the trained models (shipped in backend/artifacts; retraining needs the raw datasets, see docs/SETUP.md) =="
python -m app.ml.train check
echo "== Running tests =="
pytest -q || true
cd ../frontend
echo "== Frontend: packages =="
npm install --no-audit --no-fund
echo
echo "Setup complete. Start the app with:  ./run.sh   (or in VS Code: Cmd+Shift+B)"
echo "AI CFO: install Ollama and run 'ollama pull qwen2.5:3b' once; without it the assistant answers in calculator mode."
