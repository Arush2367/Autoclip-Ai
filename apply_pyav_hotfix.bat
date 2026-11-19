@echo off
setlocal
cd /d "%~dp0"

echo [AutoClips AI] Applying Faster-Whisper / PyAV compatibility fix...
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    echo Extract this hotfix into the AutoClips-AI project root.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m pip install --force-reinstall "av==18.1.0"
if errorlevel 1 goto :error

.venv\Scripts\python.exe -c "import av; print('PyAV version:', av.__version__); assert av.__version__ == '18.1.0', 'Unexpected PyAV version'"
if errorlevel 1 goto :error

.venv\Scripts\python.exe -m pip check
if errorlevel 1 goto :error

echo.
echo Hotfix installed successfully. Restart AutoClips AI and retry the failed analysis.
pause
exit /b 0

:error
echo.
echo Hotfix did not complete. Copy the full error output and share it.
pause
exit /b 1
