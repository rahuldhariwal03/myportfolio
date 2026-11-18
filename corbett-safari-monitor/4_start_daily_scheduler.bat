@echo off
REM ============================================================================
REM Step 4: Keep running in background to collect Morning & Evening (Asia/Kolkata)
REM Change MORNING_COLLECTION_TIME and EVENING_COLLECTION_TIME in .env anytime.
REM ============================================================================
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Please run setup_and_run.bat first.
    pause
    exit /b 1
)

echo Starting automatic Morning ^& Evening Corbett Safari scheduler (IST)...
echo Keep this window open. Press Ctrl+C anytime to stop.
echo.
.venv\Scripts\python.exe scripts\run_scheduler.py
pause
