@echo off
REM ============================================================================
REM One-Click Setup & Launcher for Windows (Corbett Safari Monitor)
REM Double-click this file or run `setup_and_run.bat` in Command Prompt.
REM ============================================================================
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

echo [1/6] Checking Python 3 installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3 is not installed or not added to PATH.
    echo Download Python 3.11+ from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/6] Creating virtual environment (.venv)...
    python -m venv .venv
) else (
    echo [2/6] Virtual environment (.venv) already exists.
)

echo [3/6] Installing required Python packages...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt

echo [4/6] Installing Playwright Chromium browser...
.venv\Scripts\playwright.exe install chromium

if not exist ".env" (
    echo [5/6] Creating .env configuration file from .env.example...
    copy .env.example .env >nul
) else (
    echo [5/6] Using existing .env configuration file.
)

echo [6/6] Initializing Live database and isolated [DEMO] sample database...
.venv\Scripts\python.exe scripts\init_db.py
.venv\Scripts\python.exe scripts\seed_demo_data.py

echo.
echo ============================================================================
echo  Starting Corbett Safari Dashboard at http://localhost:8501
echo  Press Ctrl+C in this window anytime to stop the server.
echo ============================================================================
.venv\Scripts\streamlit.exe run app.py --server.address localhost --server.port 8501
pause
