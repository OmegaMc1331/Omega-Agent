param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "OmegaAgent"),
    [string]$WorkspaceDir = (Join-Path $HOME "omega_workspace")
)

$ErrorActionPreference = "Continue"
$HadError = $false

function Ok([string]$Name, [string]$Detail = "") { Write-Host "[OK] $Name $Detail" -ForegroundColor Green }
function Warn([string]$Name, [string]$Detail = "") { Write-Host "[WARN] $Name $Detail" -ForegroundColor Yellow }
function Err([string]$Name, [string]$Detail = "") { $script:HadError = $true; Write-Host "[ERROR] $Name $Detail" -ForegroundColor Red }

function Test-ProfileOmega([string]$OmegaExe) {
    if (-not (Test-Path -LiteralPath $PROFILE)) { return $false }
    $content = Get-Content -LiteralPath $PROFILE -Raw -ErrorAction SilentlyContinue
    return $content -and $content.Contains("# >>> Omega Agent >>>") -and $content.Contains($OmegaExe)
}

Write-Host "Ω Omega Agent install doctor" -ForegroundColor Magenta

$omegaExe = Join-Path $InstallDir ".venv\Scripts\omega.exe"
$venv = Join-Path $InstallDir ".venv"
$envFile = Join-Path $InstallDir ".env"
$uiIndex = Join-Path $InstallDir "omega_control\dist\index.html"

if (Test-Path -LiteralPath $InstallDir) { Ok "InstallDir" $InstallDir } else { Err "InstallDir missing" $InstallDir }
if (Test-Path -LiteralPath $venv) { Ok ".venv" $venv } else { Err ".venv missing" $venv }
if (Test-Path -LiteralPath $omegaExe) { Ok "omega.exe" $omegaExe } else { Err "omega.exe missing" $omegaExe }
if (Test-Path -LiteralPath $envFile) { Ok ".env" $envFile } else { Err ".env missing" $envFile }
if (Test-Path -LiteralPath $WorkspaceDir) { Ok "Workspace" $WorkspaceDir } else { Err "Workspace missing" $WorkspaceDir }
if (Test-ProfileOmega $omegaExe) { Ok "PowerShell profile" "omega function installed" } else { Warn "PowerShell profile" "omega function not installed or profile not reloaded" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) { Ok "Python" (& $python.Source --version 2>&1) } else { Warn "Python" "not found in PATH" }

if (Test-Path -LiteralPath (Join-Path $InstallDir "omega_control")) {
    if (Test-Path -LiteralPath $uiIndex) { Ok "Omega Control build" $uiIndex } else { Warn "Omega Control build" "dist/index.html missing; run npm install && npm run build" }
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($codex) {
    Ok "Codex CLI" (& $codex.Source --version 2>&1)
    & $codex.Source login status *> $null
    if ($LASTEXITCODE -eq 0) { Ok "Codex auth" "authenticated" } else { Warn "Codex auth" "not authenticated; run codex login" }
} else {
    Warn "Codex CLI" "not found; install Codex CLI then run codex login"
}

try {
    $conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Warn "Port 8765" "in use by PID $($conn[0].OwningProcess)" } else { Ok "Port 8765" "available" }
} catch {
    Warn "Port 8765" "unable to inspect"
}

if ($HadError) { exit 1 }
exit 0
