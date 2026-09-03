@echo off
setlocal
cd /d "%~dp0"
title M-Flow Fleet Admin - DEMO

echo [M-Flow] Starting admin web demo...

if not exist ".venv\Scripts\python.exe" (
  echo [M-Flow] First-time setup: creating Python environment...
  py -3 -m venv .venv 2>nul
  if errorlevel 1 python -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install -q -e .
if errorlevel 1 (
  echo.
  echo Setup failed. Please check that Python 3.11+ is installed.
  pause
  exit /b 1
)

set MFLOW_MOCK_MODE=success
set VEHICLES_FILE=vehicles.example.json
set DATABASE_PATH=data\demo-web.db
set ARTIFACT_DIR=artifacts\demo

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8080'"

echo.
echo ========================================
echo  M-Flow Fleet Admin DEMO
 echo  Browser: http://127.0.0.1:8080
 echo  Close this window to stop the web app.
echo ========================================
echo.

python -m mflow_watchdog.cli dashboard --host 127.0.0.1 --port 8080

endlocal
