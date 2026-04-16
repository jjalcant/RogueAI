@echo off
setlocal
cd /d C:\RogueAI

set "ROGUE_PYTHON=python"
set "QT_IMPORT=from ui_qt.main_window import launch_qt_app"

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -c "%QT_IMPORT%" >nul 2>&1
    if not errorlevel 1 (
        set "ROGUE_PYTHON=.venv\Scripts\python.exe"
    ) else (
        python -c "%QT_IMPORT%" >nul 2>&1
        if errorlevel 1 (
            set "ROGUE_PYTHON=.venv\Scripts\python.exe"
        ) else (
            echo Using active Python because .venv cannot import the PySide6 launcher.
        )
    )
)

"%ROGUE_PYTHON%" rogue_app.py

pause
