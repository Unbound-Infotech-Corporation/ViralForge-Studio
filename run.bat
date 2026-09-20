@echo off
setlocal
cd /d "%~dp0"
if not defined TRENDFORGE_HOME set "TRENDFORGE_HOME=F:\TrendForge"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py %*
) else (
  python run.py %*
)
