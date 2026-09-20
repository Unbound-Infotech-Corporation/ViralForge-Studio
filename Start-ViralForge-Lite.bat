@echo off
setlocal
cd /d "%~dp0"
title ViralForge Studio Lite
echo.
echo  ViralForge Studio  Lite friend build
echo  =====================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ from python.org and check Add to PATH.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
  echo Installing dependencies (first run only)...
  call .venv\Scripts\python.exe -m pip install -U pip
  if exist requirements.txt (
    call .venv\Scripts\python.exe -m pip install -r requirements.txt
  ) else (
    call .venv\Scripts\python.exe -m pip install -e .
  )
)

echo Launching ViralForge Studio...
set VIRALFORGE_PACK=lite
set TRENDFORGE_CINEMA_DRY_RUN=1
if exist run.py (
  call .venv\Scripts\python.exe run.py
) else if exist -m (
  call .venv\Scripts\python.exe -m trendforge
) else (
  call .venv\Scripts\python.exe -m trendforge.app
)
if errorlevel 1 pause
