# hcscoder Update Script (Idempotent, Safe Updates)
$ErrorActionPreference = "Stop"

Write-Host "=== CHECKING PRIME AGENT UPDATES ===" -ForegroundColor Cyan

# Safe update logic: Never overwrite existing configuration or models destructively
Write-Host "Checking runtime binaries and packages..." -ForegroundColor Yellow
$PythonExe = "$PSScriptRoot\.venv\Scripts\python.exe"

uv pip install --python $PythonExe --link-mode=copy --upgrade `
    dill psutil pydantic fastapi uvicorn rich click httpx

Write-Host "Running health check after update..." -ForegroundColor Yellow
& "$PSScriptRoot\hcscoder.ps1" doctor
