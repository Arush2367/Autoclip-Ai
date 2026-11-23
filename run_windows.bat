@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)

echo Starting AutoClips AI on local loopback only...
echo Open http://127.0.0.1:8000 in your browser.
echo Press Ctrl+C in this window to stop the server.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
