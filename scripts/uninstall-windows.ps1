param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "OmegaAgent"),
    [string]$WorkspaceDir = (Join-Path $HOME "omega_workspace"),
    [switch]$KeepData,
    [switch]$RemoveData,
    [switch]$Force
)

$rootUninstaller = Join-Path (Split-Path -Parent $PSScriptRoot) "uninstall.ps1"
& powershell -ExecutionPolicy Bypass -File $rootUninstaller -InstallDir $InstallDir -WorkspaceDir $WorkspaceDir -KeepData:$KeepData -RemoveData:$RemoveData -Force:$Force
