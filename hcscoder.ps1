# hcscoder CLI shim (primary name; prime.ps1 remains as alias)
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

$PythonExe = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found. Please run .\bootstrap.ps1 first."
    exit 1
}

& $PythonExe "$PSScriptRoot\cli.py" @ArgsList
