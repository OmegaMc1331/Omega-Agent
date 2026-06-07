param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "OmegaAgent"),
    [string]$WorkspaceDir = (Join-Path $HOME "omega_workspace"),
    [string]$Branch = "main",
    [string]$RepoUrl = "https://github.com/OmegaMc1331/Omega-Agent",
    [switch]$SkipNode,
    [switch]$SkipCodex,
    [switch]$NoOpen,
    [switch]$Force,
    [switch]$DevMode
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) { Write-Host "[Omega] $Message" -ForegroundColor Cyan }
function Write-Warn([string]$Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Ok([string]$Message) { Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Err([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red }

function Test-Windows {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        Write-Err "Ce script cible Windows PowerShell / PowerShell sur Windows."
        exit 1
    }
}

function Find-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, "-3.11") }
    return $null
}

function Invoke-Python([array]$PythonCommand, [string[]]$ArgsList) {
    $exe = $PythonCommand[0]
    $prefix = @()
    if ($PythonCommand.Count -gt 1) { $prefix = $PythonCommand[1..($PythonCommand.Count - 1)] }
    & $exe @prefix @ArgsList
}

function Copy-DevSource([string]$Destination) {
    $source = $PSScriptRoot
    $exclude = @(".git", ".venv", "node_modules", "dist", ".pytest_cache", "__pycache__")
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Install-Source([string]$Destination, [string]$Repo, [string]$GitBranch, [bool]$UseDevMode) {
    if (Test-Path -LiteralPath $Destination) {
        if (-not $Force) {
            throw "InstallDir existe deja: $Destination. Relance avec -Force ou choisis un autre -InstallDir."
        }
        Write-Warn "Suppression de l'installation existante: $Destination"
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null

    if ($UseDevMode) {
        Write-Step "Copie locale du depot vers $Destination"
        Copy-DevSource $Destination
        return
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        Write-Step "Clonage git: $Repo ($GitBranch)"
        & $git.Source clone --branch $GitBranch --depth 1 $Repo $Destination
        if ($LASTEXITCODE -ne 0) { throw "git clone a echoue." }
        return
    }

    $zipUrl = "$Repo/archive/refs/heads/$GitBranch.zip"
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("omega-agent-" + [guid]::NewGuid().ToString())
    $zip = "$tmp.zip"
    Write-Warn "Git introuvable. Telechargement ZIP: $zipUrl"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    $expanded = Get-ChildItem -LiteralPath $tmp -Directory | Select-Object -First 1
    if (-not $expanded) { throw "Archive GitHub invalide." }
    Move-Item -LiteralPath $expanded.FullName -Destination $Destination
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in (Get-Content -LiteralPath $Path)) {
            $lines.Add([string]$line)
        }
    } else {
        $null = New-Item -ItemType File -Path $Path -Force
    }
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))=") {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines.Add("$Key=$Value") }
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

function Configure-Env([string]$Root, [string]$Workspace, [bool]$OpenBrowser) {
    $envPath = Join-Path $Root ".env"
    $example = Join-Path $Root ".env.example"
    if (-not (Test-Path -LiteralPath $envPath)) {
        if (Test-Path -LiteralPath $example) {
            Copy-Item -LiteralPath $example -Destination $envPath
        } else {
            New-Item -ItemType File -Path $envPath -Force | Out-Null
        }
    } elseif ($Force) {
        Write-Warn ".env existe; valeurs Omega principales mises a jour sans toucher aux secrets."
    }

    $omegaHome = Join-Path $HOME ".omega"
    $openBrowserValue = if ($OpenBrowser) { "true" } else { "false" }
    $pairs = [ordered]@{
        OMEGA_PROVIDER = "codex"
        OMEGA_MODEL = "gpt-5.5"
        OMEGA_DEFAULT_MODEL = "codex/gpt-5.5"
        OMEGA_FALLBACK_MODEL = ""
        OMEGA_MODEL_SELECTION_ENABLED = "true"
        OMEGA_MODEL_AUTH_CACHE_SECONDS = "300"
        OMEGA_MODEL_STATUS_CACHE_SECONDS = "60"
        OMEGA_WORKSPACE = $Workspace
        OMEGA_WORKSPACE_FULL_ACCESS = "true"
        OMEGA_REQUIRE_APPROVAL = "false"
        OMEGA_REQUIRE_APPROVAL_OUTSIDE_WORKSPACE = "true"
        OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE = "true"
        OMEGA_ALLOW_DELETE_IN_WORKSPACE = "true"
        OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE = "true"
        OMEGA_HOST = "127.0.0.1"
        OMEGA_PORT = "8765"
        OMEGA_OPEN_BROWSER = $openBrowserValue
        OMEGA_CHANNELS_ENABLED = "true"
        OMEGA_WEBHOOKS_ENABLED = "true"
        OMEGA_TELEGRAM_ENABLED = "false"
        OMEGA_DISCORD_ENABLED = "false"
        OMEGA_TELEGRAM_BOT_TOKEN = ""
        OMEGA_DISCORD_BOT_TOKEN = ""
        OMEGA_SCHEDULER_ENABLED = "false"
        OMEGA_SCHEDULER_TICK_SECONDS = "30"
        OMEGA_REASONING_STREAM = "true"
        OMEGA_REASONING_DETAIL = "minimal"
        OMEGA_FAST_MODE = "true"
        OMEGA_STREAMING = "true"
        OMEGA_STATUS_CACHE_SECONDS = "60"
        OMEGA_CODEX_AUTH_CACHE_SECONDS = "300"
        OMEGA_MAX_HISTORY_MESSAGES = "20"
        OMEGA_MAX_MEMORY_RESULTS = "5"
        OMEGA_MAX_SKILLS_IN_CONTEXT = "5"
        OMEGA_MAX_TOOL_DESCRIPTIONS = "20"
        OMEGA_LOAD_PLUGINS_ON_STARTUP = "true"
        OMEGA_RELOAD_PLUGINS_PER_MESSAGE = "false"
        OMEGA_RELOAD_SKILLS_PER_MESSAGE = "false"
        OMEGA_DB_PATH = (Join-Path $omegaHome "omega.db")
        OMEGA_SKILLS_DIR = (Join-Path $HOME "omega_skills")
        OMEGA_PLUGINS_DIR = (Join-Path $HOME "omega_plugins")
    }
    foreach ($key in $pairs.Keys) { Set-EnvValue $envPath $key $pairs[$key] }

    New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
    New-Item -ItemType Directory -Path $omegaHome -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $HOME "omega_skills") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $HOME "omega_plugins") -Force | Out-Null
}

Write-Host ""
Write-Host "Ω Omega Agent Installer" -ForegroundColor Magenta
Write-Host ""

Test-Windows
Write-Step "PowerShell $($PSVersionTable.PSVersion)"

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$WorkspaceDir = [System.IO.Path]::GetFullPath($WorkspaceDir)
Install-Source $InstallDir $RepoUrl $Branch ([bool]$DevMode)

$pythonCommand = Find-Python
if (-not $pythonCommand) {
    Write-Err "Python 3.11+ introuvable. Installe Python depuis https://www.python.org/downloads/windows/ puis relance ce script."
    exit 1
}
Write-Step "Creation de la venv"
Invoke-Python -PythonCommand $pythonCommand -ArgsList @("-m", "venv", (Join-Path $InstallDir ".venv"))
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
$venvPip = Join-Path $InstallDir ".venv\Scripts\pip.exe"
& $venvPython -m pip install --upgrade pip
& $venvPip install -e $InstallDir

if (Test-Path -LiteralPath (Join-Path $InstallDir "omega_control")) {
    if ($SkipNode) {
        Write-Warn "Build Omega Control saute (-SkipNode)."
    } else {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $npm) {
            Write-Warn "npm introuvable. Installe Node.js LTS puis lance: cd `"$InstallDir\omega_control`"; npm install; npm run build"
        } else {
            Write-Step "Installation et build Omega Control"
            Push-Location (Join-Path $InstallDir "omega_control")
            try {
                & $npm.Source install
                if ($LASTEXITCODE -ne 0) { throw "npm install a echoue." }
                & $npm.Source run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build a echoue." }
            } finally {
                Pop-Location
            }
        }
    }
}

Write-Step "Configuration .env et dossiers"
Configure-Env $InstallDir $WorkspaceDir (-not $NoOpen)

Write-Step "Installation de la commande globale omega"
& powershell -ExecutionPolicy Bypass -File (Join-Path $InstallDir "scripts\install-powershell-command.ps1") -InstallDir $InstallDir -Force

if (-not $SkipCodex) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($codex) {
        Write-Step "Codex CLI"
        & $codex.Source --version
        & $codex.Source login status
        if ($LASTEXITCODE -ne 0) { Write-Warn "Codex n'est pas connecte. Lance : codex login" }
    } else {
        Write-Warn "Codex CLI introuvable. Installe Codex CLI puis lance : codex login"
    }
}

Write-Step "Diagnostic installation"
$omegaExe = Join-Path $InstallDir ".venv\Scripts\omega.exe"
if (Test-Path -LiteralPath $omegaExe) {
    & $omegaExe doctor
} else {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $InstallDir "scripts\doctor-install.ps1") -InstallDir $InstallDir -WorkspaceDir $WorkspaceDir
}

Write-Host ""
Write-Ok "Installation terminee."
Write-Host "Rouvre PowerShell ou lance : . `$PROFILE"
Write-Host "Puis :"
Write-Host "  omega doctor"
Write-Host "  omega"
