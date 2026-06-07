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


def test_installer_env_defaults_are_present():
    content = (ROOT / "install.ps1").read_text(encoding="utf-8")
    expected = [
        'OMEGA_PROVIDER = "codex"',
        'OMEGA_MODEL = "gpt-5.5"',
        'OMEGA_DEFAULT_MODEL = "codex/gpt-5.5"',
        "OMEGA_WORKSPACE = $Workspace",
        'OMEGA_WORKSPACE_FULL_ACCESS = "true"',
        'OMEGA_REQUIRE_APPROVAL = "false"',
        'OMEGA_REQUIRE_APPROVAL_OUTSIDE_WORKSPACE = "true"',
        'OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE = "true"',
        'OMEGA_ALLOW_DELETE_IN_WORKSPACE = "true"',
        'OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE = "true"',
        'OMEGA_REASONING_DETAIL = "minimal"',
    ]
    for needle in expected:
        assert needle in content


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
