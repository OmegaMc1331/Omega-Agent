from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.channels.registry import ChannelsRegistry
from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_channels_registry_creates_builtins(tmp_path: Path):
    channels = {channel.id: channel for channel in ChannelsRegistry(cfg(tmp_path)).list()}

    assert {"web", "cli", "webhook", "telegram", "discord"} <= set(channels)
    assert channels["web"].enabled is True
    assert channels["cli"].enabled is True
    assert channels["telegram"].status == "not_configured"


def test_web_channel_active_by_default(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    channels = {channel["id"]: channel for channel in client.get("/api/channels").json()}

    assert channels["web"]["enabled"] is True
    assert channels["web"]["status"] == "active"
    assert channels["cli"]["enabled"] is True


def test_webhook_creates_session_and_marks_external_untrusted(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)

    class FakeRuntime:
        def __init__(self, config):
            self.config = config

        async def send_message(self, message, session_id=None, channel_id=None, untrusted_input=False, channel_type=None):
            from omega_agent.runtime.sessions import SessionsStore

            SessionsStore(self.config).add_message(
                session_id,
                "user",
                message,
                metadata={"untrusted_input": untrusted_input, "channel_id": channel_id, "channel_type": channel_type},
            )
            return "ok"

    monkeypatch.setattr("omega_agent.gateway.server.OmegaRuntime", FakeRuntime)
    client = TestClient(create_app(config))

    response = client.post(
        "/api/webhooks/webhook",
        json={"message": "hello from webhook", "external_account_id": "acct-1", "display_name": "Webhook User"},
    )

    assert response.status_code == 200
    session_id = response.json()["session_id"]
    session = client.get(f"/api/sessions/{session_id}").json()
    assert '"untrusted_input": true' in session["metadata_json"]
    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert '"untrusted_input": true' in messages[0]["metadata_json"]


def test_channel_tokens_are_not_exposed_in_api(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path, telegram_enabled=True, telegram_bot_token="telegram-secret-token")))

    payload = client.get("/api/channels").json()
    telegram = next(channel for channel in payload if channel["id"] == "telegram")

    assert "telegram-secret-token" not in str(telegram)
    assert telegram["config"]["bot_token"] == "[REDACTED]"


def test_telegram_discord_do_not_crash_without_token(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    telegram = client.post("/api/channels/telegram/test")
    discord = client.post("/api/channels/discord/test")

    assert telegram.status_code == 200
    assert discord.status_code == 200
    assert telegram.json()["status"] == "not_configured"
    assert discord.json()["status"] == "not_configured"
