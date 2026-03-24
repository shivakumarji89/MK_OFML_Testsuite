---
title: Local Distribution & Launcher
date: 2026-03-24
status: approved
---

# Local Distribution & Launcher

## Goal

Allow QA colleagues to install and run the OFML Testsuite locally without using a terminal, by sharing a zip of the project.

## Approach

Two batch scripts added to the project root. No new dependencies. No build step.

## Files

### `setup.bat` (run once after unzipping)

- Checks if `.venv` already exists; skips creation if so
- Creates virtual environment: `python -m venv .venv`
- Installs dependencies: `.venv\Scripts\pip install -r requirements.txt`
- Prints instructions to run `launch.bat`

### `launch.bat` (run each time)

- Starts the server: `.venv\Scripts\python main.py`
- Waits 2 seconds (`timeout /t 2 /nobreak`)
- Opens the browser: `start http://localhost:8080`
- Console window stays open showing live logs; closing it stops the server

## Change to `main.py`

Disable `reload=True` → `reload=False`. The file-watcher is a dev feature; colleagues don't need it and it adds overhead.

## Distribution

Share a `.zip` of the project folder excluding `.venv` and `__pycache__`. Colleagues:

1. Unzip anywhere
2. Run `setup.bat` once
3. Run `launch.bat` each time

Both scripts can be pinned as Windows desktop shortcuts.

## Out of scope

- Silent/no-console launcher (can be added later as Option C if desired)
- Auto-start on boot
- Packaging as standalone exe (PyInstaller)
