param(
    [switch]$Rebuild,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$DistIndex = Join-Path $Root "frontend\dist\index.html"
if ($Rebuild -or -not (Test-Path $DistIndex)) {
    Write-Host "[nightmare] Building frontend (frontend/dist)..." -ForegroundColor Red
    Push-Location (Join-Path $Root "frontend")
    npm run build
    Pop-Location
}

$EnvFile = Join-Path $Root "backend\.env"
$Port = "8000"
if (Test-Path $EnvFile) {
    $Match = Select-String -Path $EnvFile -Pattern "^NIGHTMARE_PORT=(\d+)" | Select-Object -First 1
    if ($Match) { $Port = $Match.Matches[0].Groups[1].Value }
}

# Stop any stale Nightmare backend listening on $Port so new code always takes effect
$StaleConns = Get-NetTCPConnection -LocalPort ([int]$Port) -State Listen -ErrorAction SilentlyContinue
foreach ($Conn in $StaleConns) {
    if ($Conn.OwningProcess -and $Conn.OwningProcess -gt 4) {
        Write-Host "[nightmare] Stopping previous backend process (PID $($Conn.OwningProcess)) on port $Port..." -ForegroundColor Yellow
        Stop-Process -Id $Conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 400
    }
}

if ($Background) {
    $PythonW = Join-Path $Root ".venv\Scripts\pythonw.exe"
    Start-Process -FilePath $PythonW -ArgumentList "-m", "backend" -WorkingDirectory $Root
    Write-Host "[nightmare] Started in background on http://127.0.0.1:$Port (logs: backend\logs\nightmare.log)" -ForegroundColor Green
} else {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    Write-Host "[nightmare] Starting unified server on http://127.0.0.1:$Port ..." -ForegroundColor Green
    & $Python -m backend
}
