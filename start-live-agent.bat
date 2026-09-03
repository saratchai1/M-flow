@echo off
setlocal
cd /d "%~dp0"
title M-Flow LIVE Local Agent

echo ==================================================
echo  M-Flow LIVE Local Agent
echo  Real checks run from THIS computer/network.
echo ==================================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo Python 3 is required.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo Then run this file again.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating local environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

call ".venv\Scripts\activate.bat"

echo [2/4] Installing/updating M-Flow agent...
python -m pip install --upgrade pip >nul
pip install -e .
if errorlevel 1 goto :fail

echo [3/4] Installing browser engine if needed...
python -m playwright install chromium
if errorlevel 1 goto :fail

echo [4/4] Starting LIVE agent...
set "MFLOW_URL=https://mflowthai.com/mflow/unuserpayment"
set "MFLOW_HEADLESS=true"
start "" "https://mflow-admin-demo.vercel.app"
echo.
echo Keep this window OPEN while using the web app.
echo The agent listens only on 127.0.0.1:8765.
echo.
python -m mflow_watchdog.local_agent
exit /b %errorlevel%

:fail
echo.
echo Setup failed. Copy the error above and send it to the developer.
pause
exit /b 1
