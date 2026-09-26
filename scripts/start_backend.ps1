# WorkFlowOS — Start Backend Server
# Run from the project root: .\scripts\start_backend.ps1

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $ProjectRoot "backend"
$Venv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "Starting WorkFlowOS Backend..." -ForegroundColor Cyan
Write-Host "Backend dir: $Backend" -ForegroundColor Gray

Set-Location $Backend
& $Venv -m uvicorn app.main:app --reload --port 8000 --log-level info
