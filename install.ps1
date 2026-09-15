# Prime Agent Installer Script
$ErrorActionPreference = "Stop"

Write-Host "=== INSTALLING PRIME AGENT DEPENDENCIES ===" -ForegroundColor Cyan

$PythonExe = "$PSScriptRoot\.venv\Scripts\python.exe"

# Install python dependencies via uv pip
Write-Host "Verifying Python dependencies..." -ForegroundColor Yellow
uv pip install --python $PythonExe --link-mode=copy `
    dill psutil pydantic fastapi uvicorn rich click httpx aiofiles `
    pytest pytest-asyncio pillow pypdf python-docx beautifulsoup4 `
    markdown numpy rank-bm25 mcp huggingface_hub torch torchvision `
    transformers sentence-transformers diffusers accelerate

Write-Host "Running diagnostics..." -ForegroundColor Yellow
& "$PSScriptRoot\prime.ps1" doctor

Write-Host "Installation and verification complete." -ForegroundColor Green
