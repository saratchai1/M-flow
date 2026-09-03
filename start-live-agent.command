#!/bin/bash
set -e
cd "$(dirname "$0")"

printf '\033]0;M-Flow LIVE Local Agent\007'
echo "=================================================="
echo " M-Flow LIVE Local Agent (macOS)"
echo " Current M-Flow API2 checker — no simulated result"
echo "=================================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required."
  echo "Install Python 3.11+ first, then run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] Creating local environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "[2/3] Installing/updating M-Flow agent..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -e .

echo "[3/3] Starting LIVE API2 agent..."
export MFLOW_URL="https://mflowthai.com/mflowspf/"
export MFLOW_HEADLESS="true"
open "https://mflow-admin-demo.vercel.app"

echo
echo "Keep this Terminal window OPEN while using the web app."
echo "The agent listens only on 127.0.0.1:8765."
echo
python -m mflow_watchdog.local_agent
