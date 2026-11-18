@echo off
REM ============================================================================
REM Step 2 (Run ONCE): Open safari.corbettgov.org in a visible local browser,
REM allow your real location, click one date, press ENTER, and confirm selectors.
REM ============================================================================
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Please run setup_and_run.bat first to install Python dependencies and Chromium.
    pause
    exit /b 1
)

.venv\Scripts\python.exe scripts\inspect_portal.py --interactive
echo.
pause
