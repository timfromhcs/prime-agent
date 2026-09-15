# hcscoder Bootstrap Script
$ErrorActionPreference = "Stop"

Write-Host "=== BOOTSTRAPPING PRIME AGENT ENVIRONMENT ===" -ForegroundColor Cyan

# 1. Check Python / uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warning "uv not found in PATH. Please install uv or Python 3.12+."
} else {
    Write-Host "[OK] uv detected." -ForegroundColor Green
}

# 2. Setup venv if missing
if (-not (Test-Path "$PSScriptRoot\.venv")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    uv venv "$PSScriptRoot\.venv" --python 3.12
} else {
    Write-Host "[OK] Python venv exists at .venv" -ForegroundColor Green
}

Write-Host "Bootstrap complete. Run .\install.ps1 to install packages." -ForegroundColor Green
