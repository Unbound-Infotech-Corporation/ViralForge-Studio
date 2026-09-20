@echo off
setlocal
title TrendForge Studio
cd /d F:\ViralForge\VisualCreatorUnbound
echo Starting TrendForge Studio...
echo Tip: for cinematic AI video, also run start_maestro.bat
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe run.py %*
) else (
  python run.py %*
)
