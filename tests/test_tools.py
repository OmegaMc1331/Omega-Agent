from pathlib import Path

import pytest

from omega_agent.config import OmegaConfig
from omega_agent.tools.files import _delete_file, _read_file, _write_file
from omega_agent.tools.shell import _run_shell


def test_write_file_requires_approval_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True)
    monkeypatch.setattr("builtins.input", lambda _: "no")

    result = _write_file(cfg, "note.txt", "contenu")

    assert result == "Ecriture refusee par l'utilisateur."
    assert not (tmp_path / "note.txt").exists()


def test_write_and_read_file_stay_in_workspace(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)

    assert _write_file(cfg, "notes/a.txt", "bonjour") == "Fichier ecrit: notes/a.txt"
    assert _read_file(cfg, "notes/a.txt") == "bonjour"
    assert (tmp_path / ".omega" / "actions.jsonl").exists()


def test_run_shell_requires_approval_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True)
    monkeypatch.setattr("builtins.input", lambda _: "no")

    result = _run_shell(cfg, "pytest")

    assert result == "Commande refusee par l'utilisateur."


def test_run_shell_rejects_unscoped_command(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)

    result = _run_shell(cfg, "python --version")

    assert result.startswith("Commande refusee:")


def test_write_file_in_workspace_without_approval_when_full_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True, workspace_full_access=True)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("approval should not be requested")))

    result = _write_file(cfg, "notes/a.txt", "bonjour")

    assert result == "Fichier ecrit: notes/a.txt"
    assert (tmp_path / "notes" / "a.txt").read_text(encoding="utf-8") == "bonjour"


def test_delete_file_in_workspace_without_approval_when_full_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "delete-me.txt"
    target.write_text("x", encoding="utf-8")
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True, workspace_full_access=True, allow_delete_in_workspace=True)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("approval should not be requested")))

    result = _delete_file(cfg, "delete-me.txt")

    assert result == "Fichier supprime: delete-me.txt"
    assert not target.exists()


def test_read_file_outside_workspace_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(PermissionError):
        _read_file(cfg, str(outside))


def test_write_file_outside_workspace_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False)

    with pytest.raises(PermissionError):
        _write_file(cfg, str(tmp_path / "outside.txt"), "x")


def test_delete_file_outside_workspace_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True)

    with pytest.raises(PermissionError):
        _delete_file(cfg, str(tmp_path / "outside.txt"))


def test_path_traversal_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False)

    with pytest.raises(PermissionError):
        _read_file(cfg, "../outside.txt")


def test_symlink_outside_workspace_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink unavailable")
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False)

    with pytest.raises(PermissionError):
        _read_file(cfg, "link.txt")


def test_sudo_refused_even_in_workspace_full_access(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True)

    result = _run_shell(cfg, "sudo ls")

    assert result.startswith("Commande refusee:")


def test_rm_rf_root_refused_even_in_workspace_full_access(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True)

    result = _run_shell(cfg, "rm -rf /")

    assert result.startswith("Commande refusee:")


def test_run_shell_in_workspace_without_approval_when_full_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True, workspace_full_access=True, shell_full_access_in_workspace=True)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("approval should not be requested")))
    captured = {}

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        captured["args"] = args
        captured["cwd"] = cwd

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr("omega_agent.tools.shell.subprocess.run", fake_run)

    result = _run_shell(cfg, "python scripts/task.py")

    assert result == "ok"
    assert captured["cwd"] == tmp_path
