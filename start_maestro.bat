@echo off
setlocal
title Maestro (standalone ? no Pinokio)
set "MAESTRO_APP=F:\pinokio\api\Maestro.git\app"
set "PY=%MAESTRO_APP%\env-rtx50\Scripts\python.exe"
if not exist "%PY%" set "PY=%MAESTRO_APP%\env\Scripts\python.exe"
if not exist "%PY%" (
  echo Could not find Maestro's Python env under:
  echo   %MAESTRO_APP%\env-rtx50
  echo   %MAESTRO_APP%\env
  pause
  exit /b 1
)
set SERVER_PORT=42130
set SERVER_NAME=127.0.0.1
echo.
echo  Maestro standalone
echo  UI / API: http://127.0.0.1:%SERVER_PORT%
echo  Pinokio is NOT required.
echo.
cd /d "%MAESTRO_APP%"
"%PY%" launch.py
echo.
echo Maestro exited. Press any key to close.
pause >nul
