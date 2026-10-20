$ErrorActionPreference = "Stop"
$TaskName = "ProjectNightmare"
$Root = Split-Path -Parent $PSScriptRoot
$PythonW = Join-Path $Root ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $PythonW)) {
    throw "Could not find $PythonW. Make sure .venv is created."
}

$DistIndex = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $DistIndex)) {
    Write-Host "[nightmare] Building frontend before registering auto-start..." -ForegroundColor Yellow
    Push-Location (Join-Path $Root "frontend")
    npm run build
    Pop-Location
}

$Action = New-ScheduledTaskAction -Execute $PythonW -Argument "-m backend" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Project Nightmare local assistant (single server)" -Force | Out-Null
Write-Host "[nightmare] Registered Task Scheduler task '$TaskName' (runs At log on via pythonw.exe)." -ForegroundColor Green

# The Ctrl+Alt+N helper is its own task: Task Scheduler waits for one action to end before the next.
$HotkeyTask = "ProjectNightmareHotkey"
$HotkeyAction = New-ScheduledTaskAction -Execute $PythonW -Argument "-m backend.hotkey" -WorkingDirectory $Root
Register-ScheduledTask -TaskName $HotkeyTask -Action $HotkeyAction -Trigger $Trigger -Settings $Settings -Description "Project Nightmare Ctrl+Alt+N window shortcut" -Force | Out-Null
Write-Host "[nightmare] Registered '$HotkeyTask' (the Ctrl+Alt+N shortcut helper)." -ForegroundColor Green
Write-Host "[nightmare] Starting task now..." -ForegroundColor Green
Start-ScheduledTask -TaskName $TaskName
