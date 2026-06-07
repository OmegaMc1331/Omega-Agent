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

$rootInstaller = Join-Path (Split-Path -Parent $PSScriptRoot) "install.ps1"
& powershell -ExecutionPolicy Bypass -File $rootInstaller -InstallDir $InstallDir -WorkspaceDir $WorkspaceDir -Branch $Branch -RepoUrl $RepoUrl -SkipNode:$SkipNode -SkipCodex:$SkipCodex -NoOpen:$NoOpen -Force:$Force -DevMode:$DevMode
