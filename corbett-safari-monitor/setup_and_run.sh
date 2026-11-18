#!/usr/bin/env bash
# ==============================================================================
# One-Click Setup & Launcher for macOS / Linux (Corbett Safari Monitor)
# Run with: bash setup_and_run.sh
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/6] Checking Python 3..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed. Install Python 3.11+ from https://www.python.org/downloads/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[2/6] Creating virtual environment (.venv)..."
  python3 -m venv .venv
else
  echo "[2/6] Virtual environment (.venv) already exists."
fi

echo "[3/6] Installing required Python packages..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "[4/6] Installing Playwright Chromium browser..."
.venv/bin/playwright install chromium

if [ ! -f ".env" ]; then
  echo "[5/6] Creating .env from .env.example..."
  cp .env.example .env
else
  echo "[5/6] Using existing .env configuration."
fi

echo "[6/6] Initializing Live database and isolated [DEMO] sample database..."
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/seed_demo_data.py

echo ""
echo "============================================================================"
echo " Launching Corbett Safari Dashboard at http://localhost:8501"
echo " Press Ctrl+C anytime to stop."
echo "============================================================================"
exec .venv/bin/streamlit run app.py --server.address localhost --server.port 8501
