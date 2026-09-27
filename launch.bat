@echo off
cd /d "%~dp0"
echo === OFML Testsuite ===
echo Starting server... Press Ctrl+C or close this window to stop.
echo.

if not exist .venv (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

:: Open browser after 3s delay in a background cmd (non-blocking)
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8090"

:: Run server in foreground so closing the window kills it
.venv\Scripts\python main.py
if errorlevel 1 (
    echo.
    echo ERROR: The server failed to start. Port 8090 may already be in use.
    echo Close any other running instances and try again.
    pause
)
