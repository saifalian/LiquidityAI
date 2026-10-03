@echo off
title LiquidityAI Launcher
cd /d "%~dp0"

echo ============================================
echo  LiquidityAI - Starting up...
echo ============================================
echo.

REM ── Try to find Python ──────────────────────
python --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=python
    goto :found_python
)

py --version >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    goto :found_python
)

echo [ERROR] Python not found in PATH.
echo Please install Python from https://python.org
echo Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1

:found_python

REM ── Install dependencies only once ──────────
if not exist ".deps_ok" (
    echo [INFO] First run: installing dependencies...
    %PYTHON% -m pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies!
        pause
        exit /b 1
    )
    echo. > .deps_ok
    echo [OK] Dependencies installed.
    echo.
)

REM ── Launch the app ──────────────────────────
echo [INFO] Launching LiquidityAI...
echo.
%PYTHON% ui_main.py
if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo [ERROR] App crashed with error code: %errorlevel%
    echo ============================================
    echo.
    pause
)
