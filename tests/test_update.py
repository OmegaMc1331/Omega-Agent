from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from omega_agent.updater import (
    OmegaUpdater,
    UpdateError,
    UpdateOptions,
    UpdateSummary,
    merge_config_defaults,
    print_update_summary,
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [shutil.which("git") or "git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


def _make_git_install(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "install"
    config_file = tmp_path / "user" / "config.json"

    remote.mkdir()
    _git(remote, "init", "--bare")
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Omega Tests")
    _git(repo, "config", "user.email", "omega-tests@example.invalid")
    _git(repo, "checkout", "-b", "main")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "omega-update-test"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    return repo, config_file


def _skip_install_steps(monkeypatch: pytest.MonkeyPatch, updater: OmegaUpdater) -> None:
    monkeypatch.setattr(updater, "_update_python", lambda: Path(sys.executable))
    monkeypatch.setattr(updater, "_merge_config_after_update", lambda _python: None)
    monkeypatch.setattr(updater, "_run_doctors", lambda _python, *, skip: "skipped")


def test_update_preserves_user_config(tmp_path: Path):
    config_file = tmp_path / "config.json"
    workspace = str(tmp_path / "personal-workspace")
    original = {
        "workspace": {
            "path": workspace,
            "full_access": False,
            "require_approval": True,
        },
        "gateway": {"port": 9911},
        "codex": {"sandbox_mode": "read-only", "approval_policy": "on-request"},
        "providers": {"custom": {"enabled": True, "models": ["local-model"]}},
        "user_setting": {"keep": "yes"},
    }
    config_file.write_bytes(
        b"\xef\xbb\xbf" + json.dumps(original, ensure_ascii=False).encode("utf-8")
    )

    merge_config_defaults(config_file)

    payload = json.loads(config_file.read_text(encoding="utf-8"))
    assert payload["workspace"]["path"] == workspace
    assert payload["workspace"]["full_access"] is False
    assert payload["workspace"]["require_approval"] is True
    assert payload["gateway"]["port"] == 9911
    assert payload["codex"] == original["codex"]
    assert payload["providers"]["custom"] == original["providers"]["custom"]
    assert payload["user_setting"] == {"keep": "yes"}
    assert not config_file.read_bytes().startswith(b"\xef\xbb\xbf")


def test_update_creates_config_backup(tmp_path: Path):
    config_file = tmp_path / "config.json"
    original = b'{"workspace":{"path":"C:\\\\omega-workspace"}}\n'
    config_file.write_bytes(original)
    updater = OmegaUpdater(tmp_path, config_file, emit=lambda _message: None)

    backup, policy_backups = updater.backup_user_files()

    assert backup is not None
    assert Path(backup).name.startswith("config.backup.")
    assert Path(backup).read_bytes() == original
    assert policy_backups == []


def test_update_refuses_dirty_tree_without_force(tmp_path: Path):
    repo, config_file = _make_git_install(tmp_path)
    (repo / "tracked.txt").write_text("local change\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("local file\n", encoding="utf-8")
    updater = OmegaUpdater(repo, config_file, emit=lambda _message: None)

    with pytest.raises(UpdateError, match="modifications locales"):
        updater.update(UpdateOptions(skip_frontend=True, skip_doctor=True))

    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "local change\n"
    assert (repo / "untracked.txt").exists()
    assert not list(config_file.parent.glob("config.backup.*.json"))


def test_update_supports_force_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo, config_file = _make_git_install(tmp_path)
    config_file.parent.mkdir()
    config_file.write_text('{"workspace":{"path":"personal"}}\n', encoding="utf-8")
    (repo / "tracked.txt").write_text("local change\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("local file\n", encoding="utf-8")
    messages: list[str] = []
    updater = OmegaUpdater(repo, config_file, emit=messages.append)
    _skip_install_steps(monkeypatch, updater)

    summary = updater.update(
        UpdateOptions(force=True, skip_frontend=True, skip_doctor=True)
    )

    assert summary.stash_ref
    assert summary.config_backup
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""
    stash_files = _git(
        repo,
        "stash",
        "show",
        "--include-untracked",
        "--name-only",
        summary.stash_ref,
    ).stdout
    assert "tracked.txt" in stash_files
    assert "untracked.txt" in stash_files
    assert any("conservees dans" in message for message in messages)


def test_update_merges_default_config_without_overwriting_user_values(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "app": {"language": "en"},
                "paths": {"db_path": "D:/runtime/custom.db"},
                "custom_section": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )

    merge_config_defaults(config_file)

    payload = json.loads(config_file.read_text(encoding="utf-8"))
    assert payload["app"]["language"] == "en"
    assert payload["paths"]["db_path"] == "D:/runtime/custom.db"
    assert payload["custom_section"] == {"enabled": True}
    assert payload["events"]["enabled"] is True
    assert payload["runtime"]["snapshots"]["enabled"] is True


def test_update_skips_frontend_when_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    frontend = tmp_path / "omega_control"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"scripts":{"build":"node build.js"}}',
        encoding="utf-8",
    )
    updater = OmegaUpdater(tmp_path, tmp_path / "config.json", emit=lambda _message: None)
    monkeypatch.setattr(
        updater,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("npm ne doit pas etre lance"),
    )

    assert updater._update_frontend(skip=True) == "skipped"


def test_update_handles_missing_node_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = tmp_path / "omega_control"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"scripts":{"build":"vite build"}}',
        encoding="utf-8",
    )
    messages: list[str] = []
    updater = OmegaUpdater(tmp_path, tmp_path / "config.json", emit=messages.append)
    monkeypatch.setattr("omega_agent.updater.shutil.which", lambda _name: None)

    assert updater._update_frontend(skip=False) == "node-missing"
    assert "Frontend non mis à jour : Node.js introuvable" in messages


def test_update_prints_summary():
    messages: list[str] = []
    summary = UpdateSummary(
        old_commit="1" * 40,
        new_commit="2" * 40,
        branch="main",
        config_backup="C:/Users/test/.omega/config.backup.json",
        stash_ref="stash@{0}",
        python_updated=True,
        frontend_status="yes",
        doctors_status="pass",
    )

    print_update_summary(summary, emit=messages.append)

    output = "\n".join(messages)
    assert "Ancien commit: 111111111111" in output
    assert "Nouveau commit: 222222222222" in output
    assert "Branche: main" in output
    assert "Python dependencies updated: yes" in output
    assert "Frontend updated: yes" in output
    assert "Doctors status: pass" in output
    assert "stash@{0}" in output
