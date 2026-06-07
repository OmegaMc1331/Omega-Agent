param(
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist")
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseName = "Omega-Agent-windows"
$Stage = Join-Path $OutputDir $ReleaseName
$ZipPath = Join-Path $OutputDir "$ReleaseName.zip"

function Write-Step([string]$Message) { Write-Host "[Omega] $Message" -ForegroundColor Cyan }

Write-Step "Preparation release"
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Write-Step "pytest"
Push-Location $ProjectRoot
try {
    pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest a echoue." }

    if (Test-Path -LiteralPath (Join-Path $ProjectRoot "omega_control")) {
        Push-Location (Join-Path $ProjectRoot "omega_control")
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) { throw "npm run build a echoue." }
        } finally {
            Pop-Location
        }
    }
} finally {
    Pop-Location
}

Write-Step "Copie fichiers release"
$robocopyArgs = @(
    $ProjectRoot,
    $Stage,
    "/E",
    "/XD", ".git", ".venv", "node_modules", ".pytest_cache", "__pycache__", "dist",
    "/XF", ".env", "*.pyc"
)
& robocopy @robocopyArgs | Out-Host
if ($LASTEXITCODE -ge 8) { throw "robocopy a echoue avec code $LASTEXITCODE." }

if (Test-Path -LiteralPath (Join-Path $Stage ".env")) {
    throw ".env ne doit pas etre inclus dans la release."
}
if (-not (Test-Path -LiteralPath (Join-Path $Stage ".env.example"))) {
    throw ".env.example manquant dans la release."
}

Write-Step "Archive $ZipPath"
if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -LiteralPath (Join-Path $Stage "*") -DestinationPath $ZipPath -Force
Write-Host "Release creee: $ZipPath" -ForegroundColor Green
