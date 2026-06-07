from pathlib import Path

from omega_agent.powershell_profile import (
    OMEGA_PROFILE_BEGIN,
    OMEGA_PROFILE_END,
    omega_profile_block,
    profile_contains_omega_block,
    remove_omega_block,
    replace_or_append_omega_block,
)
from omega_agent.config import OmegaConfig
from omega_agent.doctor import run_doctor


def test_omega_profile_block_points_to_omega_exe():
    block = omega_profile_block(Path("D:/Omega-Agent/.venv/Scripts/omega.exe"))

    assert OMEGA_PROFILE_BEGIN in block
    assert OMEGA_PROFILE_BEGIN == "# >>> Omega Agent >>>"
    assert OMEGA_PROFILE_END in block
    assert "function omega" in block
    assert 'omega.exe" @args' in block


def test_replace_or_append_omega_block_is_idempotent():
    original = "Write-Host hello\n"

    once = replace_or_append_omega_block(original, "D:/Omega-Agent/.venv/Scripts/omega.exe")
    twice = replace_or_append_omega_block(once, "D:/Omega-Agent/.venv/Scripts/omega.exe")

    assert profile_contains_omega_block(twice)
    assert twice.count(OMEGA_PROFILE_BEGIN) == 1
    assert "Write-Host hello" in twice


def test_remove_omega_block_preserves_other_profile_content():
    content = replace_or_append_omega_block("Set-Alias ll Get-ChildItem\n", "D:/Omega-Agent/.venv/Scripts/omega.exe")

    cleaned = remove_omega_block(content)

    assert OMEGA_PROFILE_BEGIN not in cleaned
    assert "Set-Alias ll Get-ChildItem" in cleaned


def test_doctor_reports_global_command_installed(tmp_path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    monkeypatch.setattr("omega_agent.doctor.codex_version", lambda: "codex")
    monkeypatch.setattr("omega_agent.doctor.codex_login_status", lambda: (True, "logged in"))
    monkeypatch.setattr("omega_agent.doctor.global_command_status", lambda: (True, "installed"))

    checks = {check.name: check.detail for check in run_doctor(cfg)}

    assert checks["Global command"] == "installed"
