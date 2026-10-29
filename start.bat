@echo off
rem Lintel: backend + dashboard on http://127.0.0.1:8002, marketing site on /site/
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install -q -r requirements.txt || exit /b 1
)
.venv\Scripts\python site\build.py >nul
start "" http://127.0.0.1:8002/
.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8002
