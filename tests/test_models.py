from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.main import models_command
from omega_agent.providers.openai_api_provider import OpenAIAPIProvider
from omega_agent.providers.ollama_provider import OllamaProvider
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.model_selector import ModelSelector


def test_legacy_provider_model_converts_to_default_model_ref(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMEGA_PROVIDER", "codex")
    monkeypatch.setenv("OMEGA_MODEL", "gpt-5.5")
    monkeypatch.delenv("OMEGA_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    cfg = OmegaConfig.from_env()

    assert cfg.default_model_ref == "codex/gpt-5.5"
    assert cfg.provider == "codex"
    assert cfg.model == "gpt-5.5"


def test_resolve_model_priority_session_project_agent_global(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, default_model_ref="codex/gpt-5.5")
    selector = ModelSelector(cfg)
    selector.set_preference("global", "codex/gpt-5.5")
    selector.set_preference("agent_profile", "openai_api/gpt-5.1-mini", scope_id="agent-1")
    selector.set_preference("project", "ollama/llama3.3", scope_id="project-1")
    selector.set_preference("session", "openrouter/anthropic/claude-sonnet-4.5", scope_id="session-1")

    resolved = selector.resolve_model(session_id="session-1", project_id="project-1", agent_profile_id="agent-1")
    assert resolved.primary_model_ref == "openrouter/anthropic/claude-sonnet-4.5"
    assert selector.resolve_model(project_id="project-1", agent_profile_id="agent-1").primary_model_ref == "ollama/llama3.3"
    assert selector.resolve_model(agent_profile_id="agent-1").primary_model_ref == "openai_api/gpt-5.1-mini"
    assert selector.resolve_model().primary_model_ref == "codex/gpt-5.5"


def test_provider_auth_status_does_not_expose_secret(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, openai_api_key="sk-secretsecretsecret")

    status = OpenAIAPIProvider(cfg).check_auth().as_api()

    assert status["status"] == "configured"
    assert "sk-secret" not in str(status)


def test_codex_provider_does_not_read_auth_json(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False)
    read_attempts = []

    def forbidden_read(*args, **kwargs):
        read_attempts.append(args)
        raise AssertionError("auth.json read")

    monkeypatch.setattr("pathlib.Path.read_text", forbidden_read)
    monkeypatch.setattr("omega_agent.codex_backend.codex_version", lambda: "codex")
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (True, "logged in"))

    from omega_agent.providers.codex_provider import CodexProvider

    assert CodexProvider(cfg).check_auth().status in {"configured", "missing"}
    assert read_attempts == []


def test_openai_disabled_without_key_does_not_crash(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False)

    assert OpenAIAPIProvider(cfg).check_auth().status == "missing"


def test_providers_without_keys_report_missing_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "not logged in"))
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False)
    selector = ModelSelector(cfg)

    statuses = {item["provider_id"]: item["status"] for item in selector.status_api(force=True)}

    assert statuses["openai_api"] == "missing"
    assert statuses["openrouter"] == "missing"
    assert statuses["anthropic"] == "missing"
    assert statuses["gemini"] == "missing"
    assert statuses["custom_openai_compatible"] == "missing"


def test_ollama_absent_does_not_crash(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, ollama_base_url="http://127.0.0.1:9")

    assert OllamaProvider(cfg).check_auth().status in {"missing", "configured"}


def test_model_fallback_triggered_if_primary_fails(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False, provider="codex")
    selector = ModelSelector(cfg)
    selector.set_preference("global", "openai_api/gpt-5.1", fallback_model_ref="codex/gpt-5.5")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "fallback ok")
    runtime = OmegaRuntime(cfg, model_selector=selector)
    session_id = runtime.sessions.create_session("Fallback").id

    output = run_async(runtime.send_message("bonjour", session_id=session_id))

    assert output == "fallback ok"
    assert any(event.type == "model.fallback" for event in runtime.events.list_recent(session_id=session_id))


def test_models_status_and_select_session_endpoint(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=False)
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "not logged in"))
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("Models").id
    client = TestClient(app)

    status = client.get("/api/models/status")
    selected = client.post("/api/models/select", json={"scope": "session", "scope_id": session, "model_ref": "ollama/llama3.3"})
    current = client.get(f"/api/models/current?session_id={session}")

    assert status.status_code == 200
    assert selected.status_code == 200
    assert current.json()["primary_model_ref"] == "ollama/llama3.3"


def test_models_status_settings_do_not_expose_secret_values(tmp_path: Path, monkeypatch):
    secret_values = [
        "sk-secretsecretsecret",
        "sk-or-v1-secretsecret",
        "sk-ant-secretsecret",
        "AIzaSecretSecretSecretSecret",
        "telegram-secret-token",
        "discord-secret-token",
        "sk-customsecretsecret",
    ]
    cfg = OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path,
        require_approval=False,
        openai_api_key=secret_values[0],
        openrouter_api_key=secret_values[1],
        anthropic_api_key=secret_values[2],
        gemini_api_key=secret_values[3],
        telegram_bot_token=secret_values[4],
        discord_bot_token=secret_values[5],
        custom_openai_base_url="https://models.local/v1",
        custom_openai_api_key=secret_values[6],
        custom_openai_model="local-pro",
    )
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "not logged in"))
    client = TestClient(create_app(cfg))

    payload = "\n".join(
        [
            str(client.get("/api/status").json()),
            str(client.get("/api/settings").json()),
            str(client.get("/api/models/status").json()),
            str(client.get("/api/models/providers").json()),
            str(client.get("/api/models/catalog").json()),
        ]
    )

    for secret in secret_values:
        assert secret not in payload


def test_omega_models_current_command_uses_default_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OMEGA_DB_PATH", str(tmp_path / "omega.db"))
    monkeypatch.setenv("OMEGA_DEFAULT_MODEL", "codex/gpt-5.5")
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "not logged in"))
    output: list[str] = []

    class FakeConsole:
        def print(self, *args, **kwargs):
            output.append(" ".join(str(arg) for arg in args))

    monkeypatch.setattr("omega_agent.main.console", FakeConsole())

    code = models_command(SimpleNamespace(models_command="current"))

    assert code == 0
    assert "codex/gpt-5.5" in "\n".join(output)


def test_model_selector_does_not_change_security_policy(tmp_path: Path):
    cfg = OmegaConfig(model="gpt-5.5", workspace=tmp_path, require_approval=True)
    selector = ModelSelector(cfg)
    selector.set_preference("global", "ollama/llama3.3")

    assert cfg.require_approval is True


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
