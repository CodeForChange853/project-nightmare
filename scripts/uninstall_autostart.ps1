$ErrorActionPreference = "Stop"

foreach ($TaskName in "ProjectNightmare", "ProjectNightmareHotkey") {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[nightmare] Removed Task Scheduler task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "[nightmare] Task '$TaskName' is not registered." -ForegroundColor Yellow
    }
}
