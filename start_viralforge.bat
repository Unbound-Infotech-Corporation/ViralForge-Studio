@echo off
setlocal
title ViralForge stack (Maestro + TrendForge)
echo Starting Maestro, then TrendForge...
start "Maestro" cmd /c "F:\ViralForge\VisualCreatorUnbound\start_maestro.bat"
timeout /t 8 /nobreak >nul
start "TrendForge" cmd /c "F:\ViralForge\VisualCreatorUnbound\start_trendforge.bat"
echo Both launched. Maestro needs ~20-40s before the API is ready.
