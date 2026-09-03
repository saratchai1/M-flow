#!/bin/bash
set -e
cd "$(dirname "$0")"

printf '\033]0;M-Flow LIVE Local Agent\007'
echo "=================================================="
echo " M-Flow LIVE Local Agent (macOS)"
echo " Real checks run from THIS Mac/network."
echo "=================================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required."
  echo "Install Python 3.11+ first, then run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/4] Creating local environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "[2/4] Installing/updating M-Flow agent..."
python -m pip install --upgrade pip >/dev/null
pip install -e .

echo "[3/4] Installing browser engine if needed..."
python -m playwright install chromium

echo "[4/4] Starting LIVE agent..."
export MFLOW_URL="https://mflowthai.com/mflow/unuserpayment"
export MFLOW_HEADLESS="true"
open "https://mflow-admin-demo.vercel.app"

echo
echo "Keep this Terminal window OPEN while using the web app."
echo "The agent listens only on 127.0.0.1:8765."
echo
python -m mflow_watchdog.local_agent
