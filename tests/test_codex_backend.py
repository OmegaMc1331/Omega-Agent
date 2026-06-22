from pathlib import Path
from types import SimpleNamespace

from omega_agent.codex_backend import CODEX_LOGIN_HINT, ensure_codex_ready, run_codex_turn
from omega_agent.config import OmegaConfig


def test_ensure_codex_ready_prompts_login_when_not_authenticated(monkeypatch):
    monkeypatch.setattr("omega_agent.codex_backend.codex_version", lambda: "codex-cli test")
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "Not logged in"))

    assert ensure_codex_ready() == CODEX_LOGIN_HINT


def test_codex_turn_uses_codex_exec_scoped_to_workspace(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, provider="codex")
    captured = {}

    monkeypatch.setattr("omega_agent.codex_backend.ensure_codex_ready", lambda: None)
    monkeypatch.setattr("omega_agent.codex_backend.shutil.which", lambda _: "codex")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("Réponse Codex", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    result = run_codex_turn(cfg, [], "Bonjour")

    assert result == "Réponse Codex"
    assert captured["command"][:2] == ["codex", "exec"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gpt-5.5"
    assert captured["command"][captured["command"].index("--cd") + 1] == str(tmp_path)
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "workspace-write"
    assert captured["command"][captured["command"].index("--ask-for-approval") + 1] == "on-request"
    assert "--ephemeral" in captured["command"]
    assert "--ignore-user-config" in captured["command"]
    assert "--ignore-rules" in captured["command"]
    assert captured["kwargs"]["cwd"] == tmp_path
    assert "OMEGA_WORKSPACE" in captured["kwargs"]["env"]
    assert captured["kwargs"]["encoding"] == "utf-8"


def test_codex_backend_uses_workspace_write_when_full_access(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        provider="codex",
        workspace_full_access=True,
    )
    captured = {}

    monkeypatch.setattr("omega_agent.codex_backend.ensure_codex_ready", lambda: None)
    monkeypatch.setattr("omega_agent.codex_backend.shutil.which", lambda _: "codex")

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("ok", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    assert run_codex_turn(cfg, [], "Crée note.txt") == "ok"
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "workspace-write"
    assert captured["command"][captured["command"].index("--ask-for-approval") + 1] == "never"


def test_codex_backend_does_not_use_read_only_when_full_access(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        provider="codex",
        workspace_full_access=True,
        codex_sandbox_mode="read-only",
    )
    captured = {}

    monkeypatch.setattr("omega_agent.codex_backend.ensure_codex_ready", lambda: None)
    monkeypatch.setattr("omega_agent.codex_backend.shutil.which", lambda _: "codex")

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("ok", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    assert run_codex_turn(cfg, [], "Modifie note.txt") == "ok"
    sandbox = captured["command"][captured["command"].index("--sandbox") + 1]
    assert sandbox == "workspace-write"
    assert "read-only" not in captured["command"]
