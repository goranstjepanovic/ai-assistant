@echo off
setlocal

echo ============================================================
echo  Nyssa setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo Found Python %PY_VER%

:: Check Ollama
curl -s -o nul http://localhost:11434/ >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Ollama does not appear to be running on localhost:11434
    echo   Start Ollama and pull a model before running Nyssa:
    echo     ollama pull gemma4
    echo.
) else (
    echo Ollama is running.
)

:: Create venv if it doesn't exist
if not exist ".venv" (
    echo.
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate and install
echo.
echo Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo ============================================================
echo  Setup complete.
echo.
echo  To start Nyssa:
echo    .venv\Scripts\activate
echo    python main.py
echo.
echo  Config is in config\settings.json
echo ============================================================
echo.
pause
