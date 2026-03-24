@echo off
cd /d "%~dp0"
echo === OFML Testsuite Setup ===
echo.

if exist .venv (
    echo Virtual environment already exists. Skipping creation.
) else (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python 3.10 or later is installed: https://www.python.org/downloads/
        echo During installation, check "Add Python to PATH".
        pause
        exit /b 1
    )
)

echo.
echo Installing dependencies...
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Setup complete! Run launch.bat to start the app.
pause
