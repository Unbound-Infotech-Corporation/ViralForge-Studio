#requires -Version 5
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .venv\Scripts\python.exe)) {
  Write-Host "Create the venv first:  powershell -File scripts\install_windows.ps1"
  exit 1
}

& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean trendforge.spec

New-Item -ItemType Directory -Force -Path release | Out-Null
Copy-Item dist\TrendForgeStudio\TrendForgeStudio.exe release\ -ErrorAction SilentlyContinue
if (Test-Path dist\TrendForgeStudio) {
  Copy-Item dist\TrendForgeStudio release\TrendForgeStudio -Recurse -Force
}
Write-Host "Build output: dist\TrendForgeStudio\TrendForgeStudio.exe"
Write-Host "Optional installer: compile installer\trendforge.iss with Inno Setup."
