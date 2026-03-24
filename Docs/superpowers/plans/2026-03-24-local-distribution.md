# Local Distribution & Launcher Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two batch scripts (`setup.bat`, `launch.bat`) so colleagues can install and run the app locally without a terminal, and disable `reload=True` in `main.py` for distribution.

**Architecture:** Pure batch scripts in the project root. `setup.bat` creates a virtual environment and installs dependencies once. `launch.bat` starts the server and opens the browser. One small change to `main.py` disables the dev file-watcher.

**Tech Stack:** Windows batch scripting, Python venv, uvicorn

---

## Chunk 1: All changes

### Task 1: Disable reload in main.py

**Files:**
- Modify: `main.py:20`

No unit test needed — this is a config value change that is verified by running the app.

- [ ] **Step 1: Edit `main.py`**

Change line 20 from:
```python
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
```
to:
```python
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
```

- [ ] **Step 2: Verify the app still starts**

Run: `python main.py`
Expected: Server starts at `http://127.0.0.1:8080`, no reload watcher message in output. Stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "chore: disable uvicorn reload for distribution"
```

---

### Task 2: Create setup.bat

**Files:**
- Create: `setup.bat`

- [ ] **Step 1: Create `setup.bat` in the project root**

```bat
@echo off
echo === OFML Testsuite Setup ===
echo.

if exist .venv (
    echo Virtual environment already exists. Skipping creation.
) else (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment. Is Python installed?
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
```

- [ ] **Step 2: Verify setup.bat works**

Delete `.venv` if it exists, then double-click `setup.bat` (or run it in a terminal).
Expected: venv is created, packages install successfully, "Setup complete" message appears.

Run it a second time.
Expected: "Virtual environment already exists. Skipping creation." — installs deps again and completes without error.

- [ ] **Step 3: Commit**

```bash
git add setup.bat
git commit -m "feat: add setup.bat for one-time local install"
```

---

### Task 3: Create launch.bat

**Files:**
- Create: `launch.bat`

- [ ] **Step 1: Create `launch.bat` in the project root**

```bat
@echo off
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
```

- [ ] **Step 2: Verify launch.bat works**

Double-click `launch.bat`.
Expected: Console window opens with the header message, browser opens to `http://localhost:8080` after ~2 seconds, app is functional. Closing the console window stops the server.

- [ ] **Step 3: Verify error case**

Rename `.venv` to `.venv_bak`, run `launch.bat`.
Expected: "Virtual environment not found" error with pause. Rename back.

- [ ] **Step 4: Commit**

```bash
git add launch.bat
git commit -m "feat: add launch.bat to start server and open browser"
```
