# One-command setup for Project Nightmare. Safe to run again: it only fills in what is missing.
#   .\scripts\install.ps1                 venv + packages, frontend build, backend\.env, apps.json
#   .\scripts\install.ps1 -Dev            also install the test tools
#   .\scripts\install.ps1 -Autostart      also start Nightmare at Windows log on
#   .\scripts\install.ps1 -Shortcut       also put a "Nightmare" shortcut on the Desktop (Chrome app window)
#   .\scripts\install.ps1 -NoPrompt       never ask for PINs (leave them empty and warn instead)
#
# It never overwrites an existing backend\.env value, apps.json or frontend\.env.local.
param(
    [switch]$Dev,
    [switch]$Autostart,
    [switch]$Shortcut,
    [switch]$NoPrompt
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root "backend\.env"
. (Join-Path $PSScriptRoot "nightmare_env.ps1")

function Step([string]$Text) { Write-Host "[nightmare] $Text" -ForegroundColor Red }
function Ok([string]$Text) { Write-Host "  $Text" -ForegroundColor Green }
function Warn([string]$Text) { Write-Host "  $Text" -ForegroundColor Yellow }

# ---- Python 3.11+ ----
Step "Checking Python..."
$Python = $null
foreach ($candidate in @(@("py", "-3"), @("python"))) {
    $exe = Get-Command $candidate[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $args_ = @($candidate | Select-Object -Skip 1)
    $ver = $null
    try { $ver = & $exe.Source @args_ -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { continue }
    if ($LASTEXITCODE -eq 0 -and $ver -and [version]$ver -ge [version]"3.11") { $Python = @($exe.Source) + $args_; break }
}
if (-not $Python) { throw "Python 3.11 or newer was not found. Install it from python.org or the Microsoft Store." }
Ok "Python $ver"

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Step "Creating .venv..."
    $pyArgs = @($Python | Select-Object -Skip 1) + @("-m", "venv", (Join-Path $Root ".venv"))
    & $Python[0] @pyArgs
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv" }
}
Step "Installing Python packages..."
$req = if ($Dev) { "backend\requirements-dev.txt" } else { "backend\requirements.txt" }
& $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $Root $req)
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Ok "Installed $req"

# ---- backend\.env ----
Step "Checking backend\.env..."
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root "backend\.env.example") $EnvFile
    Ok "Created backend\.env from .env.example"
}
if ((Get-EnvValue "NIGHTMARE_TOKEN").Length -lt 16) {
    $token = & $VenvPython -c "import secrets; print(secrets.token_urlsafe(32))"
    Set-EnvValue "NIGHTMARE_TOKEN" $token
    Ok "Generated a new NIGHTMARE_TOKEN"
}

function Read-Pin([string]$Label) {
    while ($true) {
        $secure = Read-Host "  $Label (6+ characters, Enter to skip)" -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        if (-not $plain) { return "" }
        if ($plain.Length -ge 6) { return $plain }
        Warn "Too short, try again."
    }
}

foreach ($pair in @(@("NIGHTMARE_PIN", "Laptop PIN (full access)"), @("NIGHTMARE_PHONE_PIN", "Phone PIN (read-only)"))) {
    $name, $label = $pair
    $current = Get-EnvValue $name
    if ($current) {
        if ($current.Length -lt 6) { Warn "$name is only $($current.Length) characters. 6+ is safer; edit backend\.env to change it." }
        continue
    }
    if ($NoPrompt) { Warn "$name is empty. Set it in backend\.env to use PIN login."; continue }
    $pin = Read-Pin $label
    if ($pin) { Set-EnvValue $name $pin; Ok "$name saved" } else { Warn "$name left empty." }
}
$pinA = Get-EnvValue "NIGHTMARE_PIN"
if ($pinA -and $pinA -eq (Get-EnvValue "NIGHTMARE_PHONE_PIN")) {
    Warn "The laptop and phone PINs are the same. Use different ones so the phone PIN can't unlock the laptop."
}

# ---- apps.json and the Vite dev-mode token ----
$Apps = Join-Path $Root "backend\apps.json"
if (-not (Test-Path $Apps)) {
    Copy-Item (Join-Path $Root "backend\apps.example.json") $Apps
    Ok "Created backend\apps.json from apps.example.json (edit it in Settings)"
}
$EnvLocal = Join-Path $Root "frontend\.env.local"
if (-not (Test-Path $EnvLocal)) {
    $lines = @("# Dev mode only (npm run dev). Must match NIGHTMARE_TOKEN in backend\.env.", "NIGHTMARE_TOKEN=$(Get-EnvValue 'NIGHTMARE_TOKEN')")
    [IO.File]::WriteAllLines($EnvLocal, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
    Ok "Created frontend\.env.local"
}

# ---- frontend ----
Step "Building the frontend..."
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js was not found. Install Node 22 LTS (winget install OpenJS.NodeJS.LTS)." }
$nodeVer = [version]((& node --version).TrimStart("v"))
if (-not (($nodeVer.Major -eq 20 -and $nodeVer -ge [version]"20.19") -or ($nodeVer.Major -eq 22 -and $nodeVer -ge [version]"22.12") -or $nodeVer.Major -ge 23)) {
    throw "Node $nodeVer is too old for Vite 8. Install Node 20.19+ or 22.12+."
}
Push-Location (Join-Path $Root "frontend")
try {
    if (-not (Test-Path "node_modules")) {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    }
    npm run build --silent
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally { Pop-Location }
Ok "frontend\dist is ready (Node $nodeVer)"

# ---- agy ----
if (Get-Command agy -ErrorAction SilentlyContinue) { Ok "agy found" }
else { Warn "agy (Antigravity CLI) is not on PATH. Summaries and chat need it; everything else still works." }

$Port = Get-EnvValue "NIGHTMARE_PORT" "8000"

if ($Autostart) {
    Step "Registering auto-start..."
    & (Join-Path $PSScriptRoot "install_autostart.ps1")
}

if ($Shortcut) {
    Step "Creating the Desktop shortcut..."
    $chrome = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(default)'
    if (-not $chrome) { $chrome = (Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(default)' }
    if (-not $chrome) {
        Warn "Chrome was not found, so no shortcut was made. Open http://127.0.0.1:$Port in Chrome instead."
    } else {
        $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Nightmare.lnk"
        $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
        $sc.TargetPath = $chrome
        $sc.Arguments = "--app=http://127.0.0.1:$Port/"
        $sc.Description = "Project Nightmare"
        $sc.IconLocation = "$chrome,0"
        $sc.Save()
        Ok "Desktop\Nightmare.lnk opens Nightmare in its own Chrome window"
    }
}

Write-Host ""
Write-Host "[nightmare] Ready. Start it with:  .\scripts\start_nightmare.ps1 -Background" -ForegroundColor Green
Write-Host "            then open http://127.0.0.1:$Port in Chrome." -ForegroundColor Green
