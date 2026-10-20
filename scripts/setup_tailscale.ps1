# Phone access over Tailscale (Phase 4).
#   .\scripts\setup_tailscale.ps1            share Nightmare on your tailnet over HTTPS and allow the name
#   .\scripts\setup_tailscale.ps1 -Restart   same, then restart the backend in the background
#   .\scripts\setup_tailscale.ps1 -Status    show what tailscale serve is sharing
#   .\scripts\setup_tailscale.ps1 -Off       stop sharing and clear NIGHTMARE_ALLOWED_HOSTS
#
# Uses `tailscale serve` (your own tailnet devices only). It never uses Funnel, which would put
# Nightmare on the public internet. The backend stays bound to 127.0.0.1; Tailscale proxies to it.
param(
    [switch]$Off,
    [switch]$Status,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root "backend\.env"

function Find-Tailscale {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
    if (Test-Path $default) { return $default }
    return $null
}

. (Join-Path $PSScriptRoot "nightmare_env.ps1")

$Tailscale = Find-Tailscale
if (-not $Tailscale) {
    Write-Host "[nightmare] Tailscale is not installed." -ForegroundColor Red
    Write-Host "  1. Install it:  winget install --id Tailscale.Tailscale   (or https://tailscale.com/download/windows)"
    Write-Host "  2. Sign in from the tray icon, and install the Tailscale app on your Android phone with the same account."
    Write-Host "  3. Run this script again."
    exit 1
}

$Port = Get-EnvValue "NIGHTMARE_PORT" "8000"

if ($Status) {
    & $Tailscale serve status
    Write-Host "NIGHTMARE_ALLOWED_HOSTS=$(Get-EnvValue 'NIGHTMARE_ALLOWED_HOSTS')"
    exit 0
}

if ($Off) {
    & $Tailscale serve --https=443 off
    Set-EnvValue "NIGHTMARE_ALLOWED_HOSTS" ""
    Write-Host "[nightmare] Stopped sharing. Remote access is refused after the backend restarts." -ForegroundColor Yellow
    if ($Restart) { & (Join-Path $PSScriptRoot "start_nightmare.ps1") -Background }
    exit 0
}

$Info = & $Tailscale status --json | Out-String | ConvertFrom-Json
if ($Info.BackendState -ne "Running") {
    Write-Host "[nightmare] Tailscale is not connected (state: $($Info.BackendState)). Sign in from the tray icon or run: tailscale up" -ForegroundColor Red
    exit 1
}
$DnsName = "$($Info.Self.DNSName)".TrimEnd(".").ToLower()
if (-not $DnsName) {
    Write-Host "[nightmare] This machine has no tailnet DNS name. Turn on MagicDNS in the Tailscale admin console (DNS page)." -ForegroundColor Red
    exit 1
}

$PhonePin = Get-EnvValue "NIGHTMARE_PHONE_PIN"
if (-not $PhonePin) {
    Write-Host "[nightmare] NIGHTMARE_PHONE_PIN is empty in backend\.env. Set one first (6+ digits) so the phone can log in." -ForegroundColor Red
    exit 1
}
if ($PhonePin.Length -lt 6) {
    Write-Host "[nightmare] Tip: your phone PIN is $($PhonePin.Length) digits. 6 or more is safer." -ForegroundColor Yellow
}

Write-Host "[nightmare] Sharing http://127.0.0.1:$Port as https://$DnsName (tailnet only)..." -ForegroundColor Red
# If HTTPS certificates are not enabled for the tailnet yet, this prints a link to enable them.
& $Tailscale serve --bg --https=443 "http://127.0.0.1:$Port"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[nightmare] tailscale serve failed. Enable HTTPS Certificates on the admin console DNS page, then run this again." -ForegroundColor Red
    exit 1
}

Set-EnvValue "NIGHTMARE_ALLOWED_HOSTS" $DnsName
Write-Host "[nightmare] backend\.env: NIGHTMARE_ALLOWED_HOSTS=$DnsName" -ForegroundColor Green

if ($Restart) {
    & (Join-Path $PSScriptRoot "start_nightmare.ps1") -Background
} else {
    Write-Host "[nightmare] Restart the backend so it picks this up:  .\scripts\start_nightmare.ps1 -Background" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "On your phone (Tailscale app connected), open in Chrome:" -ForegroundColor Green
Write-Host "  https://$DnsName/" -ForegroundColor Green
Write-Host "Log in with the phone PIN. Phone sessions are read-only: no opening apps, running tasks or the database viewer."
