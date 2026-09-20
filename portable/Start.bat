@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ViralForge Studio Setup  -  Lite
color 0E

echo.
echo   ViralForge Studio Setup
echo   Lite portable  -  no Wan / LTX weights in this zip
echo.

set "VF_ROOT=%~dp0"
set "VF_PY=%VF_ROOT%runtime\python.exe"
set "VF_APP=%VF_ROOT%app"
set "VF_WHEELS=%VF_ROOT%vendor\wheels"
set "VF_MARKER=%VF_ROOT%runtime\.deps-ok"
set "VIRALFORGE_PORTABLE=1"
set "VIRALFORGE_MODELS_DIR=%VF_ROOT%models"
set "PYTHONPATH=%VF_APP%;%PYTHONPATH%"
set "HF_HUB_DISABLE_XET=1"
set "HF_HUB_ENABLE_HF_TRANSFER=0"

if not exist "%VF_PY%" (
  echo  runtime\python.exe is missing.
  echo  Unzip the whole ViralForge-Lite-Portable folder, then run Start.bat again.
  echo.
  pause
  exit /b 1
)

if not exist "%VF_MARKER%" (
  echo  First launch: installing local UI libraries from vendor\wheels
  echo  This is NOT a GPU model download. No Wan or LTX weights are fetched.
  echo.
  if exist "%VF_ROOT%runtime\get-pip.py" (
    "%VF_PY%" "%VF_ROOT%runtime\get-pip.py" --no-warn-script-location --no-index --find-links="%VF_WHEELS%"
    if errorlevel 1 (
      "%VF_PY%" "%VF_ROOT%runtime\get-pip.py" --no-warn-script-location
    )
  )
  "%VF_PY%" -m pip install --no-warn-script-location --no-index --find-links="%VF_WHEELS%" PySide6_Essentials huggingface_hub
  if errorlevel 1 (
    echo.
    echo  Local wheel install failed. Trying PyPI for UI libraries only...
    "%VF_PY%" -m pip install --no-warn-script-location PySide6_Essentials huggingface_hub
  )
  if errorlevel 1 (
    echo.
    echo  Could not install UI libraries. Check internet or vendor\wheels.
    pause
    exit /b 1
  )
  echo ok>"%VF_MARKER%"
  echo.
)

echo  Opening setup with the Lite pack selected.
  echo  Regular and Maximum stay in the sidebar if you want to upgrade later.
echo.

"%VF_PY%" -m viralforge_setup --pack lite --skip-optional --models-dir "%VIRALFORGE_MODELS_DIR%"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo  Setup exited with code %ERR%.
  pause
)
exit /b %ERR%
