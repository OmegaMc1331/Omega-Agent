param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "OmegaAgent"),
    [string]$WorkspaceDir = (Join-Path $HOME "omega_workspace"),
    [switch]$KeepData,
    [switch]$RemoveData,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) { Write-Host "[Omega] $Message" -ForegroundColor Cyan }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Confirm-Action([string]$Prompt) {
    if ($Force) { return $true }
    $answer = Read-Host "$Prompt (yes/no)"
    return $answer.Trim().ToLowerInvariant() -in @("y", "yes", "o", "oui")
}

function Remove-OmegaProfileBlock {
    $profilePath = $PROFILE
    if (-not (Test-Path -LiteralPath $profilePath)) { return }
    $content = Get-Content -LiteralPath $profilePath -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { return }
    $markers = @(
        @("# >>> Omega Agent >>>", "# <<< Omega Agent <<<"),
        @("# >>> Omega Agent global command >>>", "# <<< Omega Agent global command <<<")
    )
    foreach ($pair in $markers) {
        $begin = [regex]::Escape($pair[0])
        $end = [regex]::Escape($pair[1])
        $pattern = "(?ms)^$begin.*?^$end\r?\n?"
        $content = [regex]::Replace($content, $pattern, "")
    }
    Set-Content -LiteralPath $profilePath -Value $content -Encoding UTF8
}

function Stop-OmegaGateway {
    $connections = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    } catch {
        return
    }
    foreach ($conn in $connections) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $path = ""
        try { $path = $proc.Path } catch { $path = "" }
        $looksOmega = ($path -like "*OmegaAgent*" -or $path -like "*Omega-Agent*" -or $proc.ProcessName -like "*omega*")
        if ($looksOmega -and (Confirm-Action "Arreter Omega Gateway PID $($proc.Id) ?")) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}

Write-Host ""
Write-Host "Ω Omega Agent Uninstaller" -ForegroundColor Magenta
Write-Host ""

Write-Step "Arret eventuel de Omega Gateway"
Stop-OmegaGateway

Write-Step "Suppression de la commande globale omega"
Remove-OmegaProfileBlock

if (Test-Path -LiteralPath $InstallDir) {
    if (Confirm-Action "Supprimer l'installation $InstallDir ?") {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
        Write-Host "Installation supprimee: $InstallDir"
    }
}

if ($RemoveData) {
    $omegaHome = Join-Path $HOME ".omega"
    foreach ($path in @($omegaHome, $WorkspaceDir)) {
        if (Test-Path -LiteralPath $path) {
            if (Confirm-Action "Supprimer les donnees utilisateur $path ?") {
                Remove-Item -LiteralPath $path -Recurse -Force
                Write-Host "Donnees supprimees: $path"
            }
        }
    }
} else {
    Write-Warn "Donnees conservees. Utilise -RemoveData pour supprimer $HOME\.omega et $WorkspaceDir."
}

Write-Host "Desinstallation terminee. Rouvre PowerShell ou lance : . `$PROFILE"
