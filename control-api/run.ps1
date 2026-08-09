# Convenience launcher for the control-API.
# Assumes: `python -m venv .venv` + `pip install -r requirements.txt` was done once.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$venvActivate = Join-Path $here '.venv\Scripts\Activate.ps1'
if (-not (Test-Path $venvActivate)) {
    Write-Host "No .venv found. Run these once first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  pip install -r requirements.txt"
    exit 1
}
. $venvActivate

uvicorn server:app --host 127.0.0.1 --port 8080 --reload
