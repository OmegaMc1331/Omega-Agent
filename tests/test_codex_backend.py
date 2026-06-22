from pathlib import Path
from types import SimpleNamespace

from omega_agent.codex_backend import (
    CODEX_LOGIN_HINT,
    build_codex_exec_command,
    ensure_codex_ready,
    run_codex_turn,
)
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
    monkeypatch.setattr("omega_agent.codex_backend.codex_supports_global_runtime_flags", lambda _: True)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("Réponse Codex", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    result = run_codex_turn(cfg, [], "Bonjour")

    assert result == "Réponse Codex"
    assert captured["command"][0] == "codex"
    assert captured["command"].index("--cd") < captured["command"].index("exec")
    assert captured["command"].index("--sandbox") < captured["command"].index("exec")
    assert captured["command"].index("--ask-for-approval") < captured["command"].index("exec")
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
    monkeypatch.setattr("omega_agent.codex_backend.codex_supports_global_runtime_flags", lambda _: True)

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
    monkeypatch.setattr("omega_agent.codex_backend.codex_supports_global_runtime_flags", lambda _: True)

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


def test_codex_command_puts_global_flags_before_exec(tmp_path: Path):
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        provider="codex",
        workspace_full_access=True,
    )

    command = build_codex_exec_command(
        "codex",
        cfg,
        tmp_path / ".omega" / "last-message.txt",
        supports_global_runtime_flags=True,
    )

    exec_index = command.index("exec")
    assert command[:exec_index] == [
        "codex",
        "--cd",
        str(tmp_path),
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
    ]


def test_codex_backend_never_places_ask_for_approval_after_exec(tmp_path: Path):
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        provider="codex",
        workspace_full_access=True,
    )

    command = build_codex_exec_command(
        "codex",
        cfg,
        tmp_path / ".omega" / "last-message.txt",
        supports_global_runtime_flags=True,
    )

    assert command.index("--ask-for-approval") < command.index("exec")
    assert "--ask-for-approval" not in command[command.index("exec") + 1 :]


def test_codex_backend_falls_back_to_config_toml_if_flag_unsupported(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        provider="codex",
        workspace_full_access=True,
    )
    captured = {}
    secret_prompt = "Utilise le token secret-ne-pas-logger"

    monkeypatch.setattr("omega_agent.codex_backend.ensure_codex_ready", lambda: None)
    monkeypatch.setattr("omega_agent.codex_backend.shutil.which", lambda _: "codex")
    monkeypatch.setattr("omega_agent.codex_backend.codex_supports_global_runtime_flags", lambda _: False)

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("ok", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    assert run_codex_turn(cfg, [], secret_prompt) == "ok"
    command = captured["command"]
    exec_index = command.index("exec")
    assert "--ask-for-approval" not in command
    assert "--sandbox" not in command
    assert 'sandbox_mode="workspace-write"' in command[:exec_index]
    assert 'approval_policy="never"' in command[:exec_index]
    assert secret_prompt not in command

    action_log = (tmp_path / ".omega" / "actions.jsonl").read_text(encoding="utf-8")
    assert "config-overrides" in action_log
    assert secret_prompt not in action_log
