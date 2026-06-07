param(
    [string]$ProfilePath = $PROFILE
)

$ErrorActionPreference = "Stop"

$BeginMarker = "# >>> Omega Agent >>>"
$EndMarker = "# <<< Omega Agent <<<"
$LegacyBeginMarker = "# >>> Omega Agent global command >>>"
$LegacyEndMarker = "# <<< Omega Agent global command <<<"

if (-not (Test-Path -LiteralPath $ProfilePath)) {
    Write-Host "Aucun profil PowerShell trouve. Rien a supprimer."
    exit 0
}

$Content = Get-Content -LiteralPath $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($null -eq $Content) { $Content = "" }

function Remove-MarkedBlock([string]$Text, [string]$Begin, [string]$End) {
    $beginRegex = [regex]::Escape($Begin)
    $endRegex = [regex]::Escape($End)
    $pattern = "(?ms)^$beginRegex.*?^$endRegex\r?\n?"
    return [regex]::Replace($Text, $pattern, "")
}

$NewContent = Remove-MarkedBlock $Content $BeginMarker $EndMarker
$NewContent = Remove-MarkedBlock $NewContent $LegacyBeginMarker $LegacyEndMarker

if ($NewContent -eq $Content) {
    Write-Host "Bloc Omega introuvable dans `$PROFILE. Rien a supprimer."
    exit 0
}

Set-Content -LiteralPath $ProfilePath -Value $NewContent -Encoding UTF8
Write-Host "Commande globale Omega supprimee de `$PROFILE. Rouvre PowerShell ou lance : . `$PROFILE"
