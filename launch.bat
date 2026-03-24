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

:: Open browser after 2s delay in a background cmd (non-blocking)
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8080"

:: Run server in foreground so closing the window kills it
.venv\Scripts\python main.py
