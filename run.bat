@echo off
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt

if not exist backend\.env (
    copy backend\.env.example backend\.env >nul
)

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:8000/"
uvicorn backend.main:app --reload
