#requires -Version 5
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  py -3.12 -m venv .venv 2>$null
  if (-not (Test-Path .venv\Scripts\python.exe)) { py -3.11 -m venv .venv 2>$null }
}
if (-not (Test-Path .venv\Scripts\python.exe)) {
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Installed. Run .\run.bat  or  .\.venv\Scripts\python.exe run.py"
Write-Host "Optional: winget install Gyan.FFmpeg   (imageio-ffmpeg is already a fallback)"
Write-Host "Optional: Pinokio + Maestro from https://pinokio.computer  and  https://github.com/Blizaine/Maestro"
Write-Host "Optional: Ollama from https://ollama.com/download  then  ollama pull qwen2.5:7b"
