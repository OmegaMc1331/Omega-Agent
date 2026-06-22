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

function Configure-OmegaConfig([string]$Root, [string]$Workspace, [bool]$OpenBrowser) {
    $omegaHome = Join-Path $HOME ".omega"
    New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
    New-Item -ItemType Directory -Path $omegaHome -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $HOME "omega_skills") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $HOME "omega_plugins") -Force | Out-Null
    $configPath = Join-Path $omegaHome "config.json"
    if ((Test-Path -LiteralPath $configPath) -and -not $Force) {
        Write-Warn "config.json existe deja; il n'est pas ecrase: $configPath"
        return
    }
    $config = [ordered]@{
        version = 1
        app = [ordered]@{ name = "Omega Agent"; language = "fr"; open_browser = $OpenBrowser; ui_theme = "dark" }
        gateway = [ordered]@{ host = "127.0.0.1"; port = 8765 }
        mobile = [ordered]@{ mode = "tailscale" }
        workspace = [ordered]@{
            path = $Workspace
            full_access = $true
            require_approval = $false
            require_approval_outside_workspace = $true
            shell_full_access = $true
            allow_delete = $true
            allow_git_write = $true
        }
        model = [ordered]@{ selection_enabled = $true; default = "codex/gpt-5.5"; fallback = $null; auth_cache_seconds = 300; status_cache_seconds = 60 }
        providers = [ordered]@{
            codex = [ordered]@{ enabled = $true; auth = [ordered]@{ type = "codex_oauth" }; models = @("gpt-5.5") }
            openai_api = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "secret_ref"; secret = "OPENAI_API_KEY" }; base_url = $null; models = @() }
            openrouter = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "secret_ref"; secret = "OPENROUTER_API_KEY" }; base_url = "https://openrouter.ai/api/v1"; models = @() }
            ollama = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "none" }; base_url = "http://127.0.0.1:11434"; models = @() }
            anthropic = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "secret_ref"; secret = "ANTHROPIC_API_KEY" }; models = @() }
            gemini = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "secret_ref"; secret = "GEMINI_API_KEY" }; models = @() }
            custom_openai_compatible = [ordered]@{ enabled = $false; auth = [ordered]@{ type = "secret_ref"; secret = "CUSTOM_OPENAI_API_KEY" }; base_url = $null; models = @() }
        }
        channels = [ordered]@{
            enabled = $true
            webhooks_enabled = $true
            telegram = [ordered]@{ enabled = $false; token_secret = "OMEGA_TELEGRAM_BOT_TOKEN" }
            discord = [ordered]@{ enabled = $false; token_secret = "OMEGA_DISCORD_BOT_TOKEN" }
        }
        scheduler = [ordered]@{ enabled = $false; tick_seconds = 30 }
        reasoning = [ordered]@{ stream = $true; detail = "minimal" }
        research = [ordered]@{
            enabled = $true
            max_sources = 20
            max_claims = 50
            require_evidence_for_claims = $true
            export_dir = "research_reports"
            web_enabled = $false
            external_sources_untrusted = $true
        }
        skills = [ordered]@{
            enabled = $true
            foundry_enabled = $true
            auto_detect_candidates = $false
            min_successful_runs_for_candidate = 2
            require_user_approval_for_promotion = $true
            max_skills_in_context = 5
            test_before_activation = $true
        }
        governance = [ordered]@{
            budgets = [ordered]@{
                enabled = $true
                default_profile = "Default Local"
                enforce = $true
                warning_threshold = 0.8
            }
            risk_governor = [ordered]@{
                enabled = $true
                default_max_risk = "high"
            }
        }
        shadow = [ordered]@{
            enabled = $true
            require_for_high_risk = $true
            require_for_workflows_over_steps = 5
            workspace_keep_days = 3
            max_shadow_seconds = 300
            allow_shell_in_shadow = $true
            auto_promote_low_risk = $false
            compare_after_live = $true
        }
        performance = [ordered]@{
            fast_mode = $true; streaming = $true; status_cache_seconds = 60
            max_history_messages = 20; max_memory_results = 5; max_skills_in_context = 5; max_tool_descriptions = 20
            load_plugins_on_startup = $true; reload_plugins_per_message = $false; reload_skills_per_message = $false
        }
        paths = [ordered]@{
            skills_dir = (Join-Path $HOME "omega_skills")
            plugins_dir = (Join-Path $HOME "omega_plugins")
            db_path = (Join-Path $omegaHome "omega.db")
        }
    }
    $json = $config | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText($configPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
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

Write-Step "Configuration config.json et dossiers"
Configure-OmegaConfig $InstallDir $WorkspaceDir (-not $NoOpen)

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
    & $omegaExe config doctor
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
