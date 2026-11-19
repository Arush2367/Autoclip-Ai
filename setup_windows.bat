@echo off
setlocal
cd /d "%~dp0"

echo [AutoClips AI] Checking Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 was not found. Install Python 3.10+ and enable the Python launcher.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [AutoClips AI] Creating virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :error
)

echo [AutoClips AI] Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Setup complete. Double-click run_windows.bat to start AutoClips AI.
pause
exit /b 0

:error
echo.
echo Setup failed. Read the error above and share it for troubleshooting.
pause
exit /b 1
