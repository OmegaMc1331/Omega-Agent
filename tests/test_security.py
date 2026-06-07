from pathlib import Path

import pytest

from omega_agent.config import OmegaConfig
from omega_agent.security import log_action, parse_command, safe_path


def test_safe_path_rejects_traversal(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    with pytest.raises(PermissionError):
        safe_path(cfg, "../secret.txt")


def test_safe_path_allows_workspace_file(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    assert safe_path(cfg, "notes/a.txt") == (tmp_path / "notes" / "a.txt").resolve()


@pytest.mark.parametrize(
    "relative_path",
    [".ssh/id_rsa", ".env", "notes/api_token.txt", "browser/Login Data"],
)
def test_safe_path_rejects_sensitive_names(tmp_path: Path, relative_path: str):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    with pytest.raises(PermissionError):
        safe_path(cfg, relative_path)


def test_parse_command_rejects_sudo():
    with pytest.raises(PermissionError):
        parse_command("sudo ls")


def test_parse_command_rejects_interpreters():
    with pytest.raises(PermissionError):
        parse_command("python --version")


@pytest.mark.parametrize(
    "command",
    [
        "cat ../secret.txt",
        "cat ~/.ssh/id_rsa",
        "pytest C:/Users/alexandre/project",
        "ls notes | type",
        "git -C ../other status",
        "git clone https://example.test/repo.git",
    ],
)
def test_parse_command_rejects_higher_risk_args(command: str):
    with pytest.raises(PermissionError):
        parse_command(command)


@pytest.mark.parametrize("command", ["pytest", "pytest tests", "git status", "git diff", "ls notes"])
def test_parse_command_allows_scoped_allowlist(command: str):
    assert parse_command(command)[0] in {"pytest", "git", "ls"}


def test_log_action_writes_jsonl_under_workspace(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    log_action(cfg, "unit_test", {"path": "notes/a.txt"})

    log_file = tmp_path / ".omega" / "actions.jsonl"
    assert log_file.exists()
    assert '"action": "unit_test"' in log_file.read_text(encoding="utf-8")
