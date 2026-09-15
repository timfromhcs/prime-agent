<#
.SYNOPSIS
  Prime Agent V3 one-line installer for Windows (no git clone needed).
.EXAMPLE
  irm https://raw.githubusercontent.com/timfromhcs/prime-agent/main/install.ps1 | iex
#>
param(
  [string]$InstallDir = "$env:USERPROFILE\prime-agent",
  [string]$Repo = "timfromhcs/prime-agent",
  [string]$Branch = "main",
  [switch]$SkipModels,
  [switch]$SkipLlamaCpp,
  [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"

Write-Host "=== PRIME AGENT V3 INSTALLER (Windows) ===" -ForegroundColor Cyan

# 1. Python 3.12+
$PythonCmd = $null
foreach ($c in @("py -3.12", "python")) {
  try {
    $v = Invoke-Expression "$c --version 2>&1"
    if ($v -match "3\.1[2-9]") { $PythonCmd = $c; break }
  } catch { }
}
if (-not $PythonCmd) { throw "Python 3.12+ required. Install from https://www.python.org/downloads/ and retry." }
Write-Host "[OK] Python: $(Invoke-Expression "$PythonCmd --version")" -ForegroundColor Green

# 2. Download source (zip, no git needed)
$ZipUrl = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
$TmpZip = "$env:TEMP\prime-agent-src.zip"
Write-Host "Downloading source: $ZipUrl" -ForegroundColor Yellow
Invoke-WebRequest -Uri $ZipUrl -OutFile $TmpZip
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }
$TmpDir = "$env:TEMP\prime-agent-extract"
if (Test-Path $TmpDir) { Remove-Item -Recurse -Force $TmpDir }
Expand-Archive -Path $TmpZip -DestinationPath $TmpDir
$SrcDir = Get-ChildItem $TmpDir | Select-Object -First 1 -ExpandProperty FullName
Copy-Item "$SrcDir\*" $InstallDir -Recurse -Force
Remove-Item -Recurse -Force $TmpDir, $TmpZip
Write-Host "[OK] Source -> $InstallDir" -ForegroundColor Green

# 3. Virtualenv + dependencies (validates pyproject.toml)
$VenvPy = "$InstallDir\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
  Write-Host "Creating venv..." -ForegroundColor Yellow
  Invoke-Expression "$PythonCmd -m venv `"$InstallDir\.venv`""
}
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install "$InstallDir"
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

# 4. Binaries: GGUF models (~7.5 GB) + llama.cpp (CPU + Vulkan)
if (-not $SkipModels) {
  Write-Host "Fetching GGUF models (SHA256-verified, ~7.5 GB)..." -ForegroundColor Yellow
  & $VenvPy "$InstallDir\scripts\fetch_binaries.py" --models --tiny-sd --repo-root $InstallDir
}
if (-not $SkipLlamaCpp) {
  Write-Host "Fetching llama.cpp runtimes..." -ForegroundColor Yellow
  & $VenvPy "$InstallDir\scripts\fetch_binaries.py" --llamacpp --repo-root $InstallDir
}

# 5. User PATH: prime-agent console script
$ScriptsDir = "$InstallDir\.venv\Scripts"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$ScriptsDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$UserPath;$ScriptsDir", "User")
  Write-Host "[OK] Added to user PATH (new terminals): $ScriptsDir" -ForegroundColor Green
}

# 6. Verify
if (-not $SkipDoctor) {
  Write-Host "Running diagnostics..." -ForegroundColor Yellow
  & $VenvPy "$InstallDir\cli.py" doctor
}

Write-Host ""
Write-Host "INSTALL COMPLETE. Try:" -ForegroundColor Green
Write-Host "  prime-agent tui            # workbench (new terminal for PATH)"
Write-Host "  prime-agent --help         # all commands"
Write-Host "  prime-agent doctor         # re-verify"
