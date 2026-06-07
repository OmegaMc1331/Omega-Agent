param(
    [string]$InstallDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ProfilePath = $PROFILE,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$InstallDir = (Resolve-Path -LiteralPath $InstallDir).Path
$OmegaExe = Join-Path $InstallDir ".venv\Scripts\omega.exe"
$BeginMarker = "# >>> Omega Agent >>>"
$EndMarker = "# <<< Omega Agent <<<"
$LegacyBeginMarker = "# >>> Omega Agent global command >>>"
$LegacyEndMarker = "# <<< Omega Agent global command <<<"

if (-not (Test-Path -LiteralPath $OmegaExe)) {
    Write-Error "omega.exe introuvable: $OmegaExe. Cree la venv puis lance: pip install -e ."
}

$ProfileDir = Split-Path -Parent $ProfilePath
if (-not (Test-Path -LiteralPath $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $ProfilePath)) {
    New-Item -ItemType File -Path $ProfilePath -Force | Out-Null
}

$Content = Get-Content -LiteralPath $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($null -eq $Content) { $Content = "" }

$Block = @"
$BeginMarker
function omega {
    & "$OmegaExe" @args
}
$EndMarker
"@

function Remove-MarkedBlock([string]$Text, [string]$Begin, [string]$End) {
    $beginRegex = [regex]::Escape($Begin)
    $endRegex = [regex]::Escape($End)
    $pattern = "(?ms)^$beginRegex.*?^$endRegex\r?\n?"
    return [regex]::Replace($Text, $pattern, "")
}

$HadMarkedBlock = ($Content.Contains($BeginMarker) -and $Content.Contains($EndMarker)) -or ($Content.Contains($LegacyBeginMarker) -and $Content.Contains($LegacyEndMarker))
$Content = Remove-MarkedBlock $Content $BeginMarker $EndMarker
$Content = Remove-MarkedBlock $Content $LegacyBeginMarker $LegacyEndMarker

if (-not $HadMarkedBlock -and $Content -match "(?im)^\s*function\s+(global:)?omega\s*\{" -and -not $Force) {
    $answer = Read-Host "Une fonction omega existe deja dans `$PROFILE. La remplacer par Omega Agent ? (yes/no)"
    if ($answer.Trim().ToLowerInvariant() -notin @("y", "yes", "o", "oui")) {
        Write-Host "Installation annulee. Aucune modification du profil."
        exit 0
    }
}

if (-not $HadMarkedBlock -and $Content -match "(?im)^\s*function\s+(global:)?omega\s*\{") {
    $Content = [regex]::Replace($Content, "(?im)^(\s*function\s+)(global:)?omega(\s*\{)", '${1}omega_previous${3}', 1)
}

$NewContent = $Content.TrimEnd() + $(if ($Content.Trim()) { "`r`n`r`n" } else { "" }) + $Block + "`r`n"
Set-Content -LiteralPath $ProfilePath -Value $NewContent -Encoding UTF8

Write-Host "Omega est disponible globalement. Rouvre PowerShell ou lance : . `$PROFILE"
