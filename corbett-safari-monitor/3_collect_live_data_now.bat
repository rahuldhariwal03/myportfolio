@echo off
REM ============================================================================
REM Step 3: Run ONE immediate read-only live collection into data\corbett_monitor.db
REM ============================================================================
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Please run setup_and_run.bat first.
    pause
    exit /b 1
)

echo Running live read-only availability collection (rolling 30-day window)...
.venv\Scripts\python.exe scripts\run_collector.py --type manual
echo.
echo Done! Refresh http://localhost:8501 (Live Database mode) to see your live data.
pause
