from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_scripts_exist():
    for relative in [
        "install.ps1",
        "uninstall.ps1",
        "scripts/install-windows.ps1",
        "scripts/uninstall-windows.ps1",
        "scripts/install-powershell-command.ps1",
        "scripts/doctor-install.ps1",
        "scripts/build-release.ps1",
    ]:
        assert (ROOT / relative).exists(), relative


def test_installer_config_defaults_are_present():
    content = (ROOT / "install.ps1").read_text(encoding="utf-8")
    expected = [
        'default = "codex/gpt-5.5"',
        "path = $Workspace",
        "full_access = $true",
        "require_approval = $false",
        "require_approval_outside_workspace = $true",
        "shell_full_access = $true",
        "allow_delete = $true",
        "allow_git_write = $true",
        'detail = "minimal"',
        '"config.json"',
    ]
    for needle in expected:
        assert needle in content
    assert "Configuration .env" not in content
    assert "WriteAllText($configPath" in content
    assert "UTF8Encoding]::new($false)" in content
    assert "Set-Content -LiteralPath $configPath" not in content


def test_installer_recommended_repo_and_paths_are_present():
    content = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "https://github.com/OmegaMc1331/Omega-Agent" in content
    assert '$env:LOCALAPPDATA "OmegaAgent"' in content
    assert '$HOME "omega_workspace"' in content
    assert "codex login" in content


def test_uninstall_only_targets_marked_profile_block():
    content = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")

    assert "# >>> Omega Agent >>>" in content
    assert "# <<< Omega Agent <<<" in content
    assert "Remove-OmegaProfileBlock" in content
    assert "$HOME \".omega\"" in content
    assert "RemoveData" in content
