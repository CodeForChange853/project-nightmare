# Shared helpers for reading and writing backend\.env. Dot-source it: . "$PSScriptRoot\nightmare_env.ps1"
# Expects $EnvFile to be set by the caller.

function Get-EnvValue([string]$Name, [string]$Default = "") {
    if (-not (Test-Path $EnvFile)) { return $Default }
    $m = Select-String -Path $EnvFile -Pattern "^$Name=(.*)$" | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value.Trim() }
    return $Default
}

# Replace or append NAME=value, written as UTF-8 without a BOM (python-dotenv safe).
function Set-EnvValue([string]$Name, [string]$Value) {
    $lines = @()
    if (Test-Path $EnvFile) { $lines = @([IO.File]::ReadAllLines($EnvFile)) }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$Name=") { $lines[$i] = "$Name=$Value"; $found = $true }
    }
    if (-not $found) { $lines += "$Name=$Value" }
    [IO.File]::WriteAllLines($EnvFile, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}
