from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.channels.base import EXTERNAL_CHANNEL_TYPES, ChannelAdapter, configured_status
from omega_agent.channels.cli import CliChannel
from omega_agent.channels.discord import DiscordChannel
from omega_agent.channels.telegram import TelegramChannel
from omega_agent.channels.web import WebChannel
from omega_agent.channels.webhook import WebhookChannel
from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import DEFAULT_AGENT_PROFILE_ID
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

CHANNEL_TYPES = {"web", "cli", "webhook", "telegram", "discord"}
ADAPTERS: dict[str, ChannelAdapter] = {
    "web": WebChannel(),
    "cli": CliChannel(),
    "webhook": WebhookChannel(),
    "telegram": TelegramChannel(),
    "discord": DiscordChannel(),
}


@dataclass(frozen=True)
class Channel:
    id: str
    type: str
    name: str
    enabled: bool
    status: str
    config_json: str
    created_at: str
    updated_at: str

    @property
    def config(self) -> dict:
        try:
            payload = json.loads(self.config_json)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @property
    def external(self) -> bool:
        return self.type in EXTERNAL_CHANNEL_TYPES

    def as_api(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "enabled": self.enabled,
            "status": self.status,
            "configured": self.status in {"active", "configured"},
            "external": self.external,
            "untrusted": self.external,
            "config": redact(self.config),
            "config_json": json.dumps(redact(self.config), ensure_ascii=False),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ChannelAccount:
    id: str
    channel_id: str
    external_account_id: str
    display_name: str
    route_to_agent: str
    metadata_json: str

    @property
    def metadata(self) -> dict:
        try:
            payload = json.loads(self.metadata_json)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


class ChannelsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass
        self.ensure_builtin_channels()

    def ensure_builtin_channels(self) -> None:
        specs = [
            {
                "id": "web",
                "type": "web",
                "name": "WebChat",
                "enabled": self.config.channels_enabled,
                "config": {"route_to_agent": DEFAULT_AGENT_PROFILE_ID},
            },
            {
                "id": "cli",
                "type": "cli",
                "name": "CLI",
                "enabled": self.config.channels_enabled,
                "config": {"route_to_agent": DEFAULT_AGENT_PROFILE_ID},
            },
            {
                "id": "webhook",
                "type": "webhook",
                "name": "Local Webhook",
                "enabled": self.config.channels_enabled and self.config.webhooks_enabled,
                "config": {"route_to_agent": DEFAULT_AGENT_PROFILE_ID, "enabled": self.config.webhooks_enabled},
            },
            {
                "id": "telegram",
                "type": "telegram",
                "name": "Telegram",
                "enabled": self.config.channels_enabled and self.config.telegram_enabled and bool(self.config.telegram_bot_token),
                "config": {"route_to_agent": DEFAULT_AGENT_PROFILE_ID, "bot_token": self.config.telegram_bot_token},
            },
            {
                "id": "discord",
                "type": "discord",
                "name": "Discord",
                "enabled": self.config.channels_enabled and self.config.discord_enabled and bool(self.config.discord_bot_token),
                "config": {"route_to_agent": DEFAULT_AGENT_PROFILE_ID, "bot_token": self.config.discord_bot_token},
            },
        ]
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            for spec in specs:
                row = conn.execute("SELECT id FROM channels WHERE id = ?", (spec["id"],)).fetchone()
                status = configured_status(spec["type"], spec["config"])
                if not spec["enabled"]:
                    status = "not_configured" if spec["type"] in {"telegram", "discord"} and not spec["config"].get("bot_token") else "disabled"
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO channels(id, type, name, enabled, status, config_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (spec["id"], spec["type"], spec["name"], int(spec["enabled"]), status, json.dumps(spec["config"], ensure_ascii=False), now, now),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE channels
                        SET type = ?, name = ?, enabled = ?, status = ?, config_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (spec["type"], spec["name"], int(spec["enabled"]), status, json.dumps(spec["config"], ensure_ascii=False), now, spec["id"]),
                    )

    def list(self) -> list[Channel]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT id, type, name, enabled, status, config_json, created_at, updated_at FROM channels ORDER BY id"
            ).fetchall()
        return [self._channel_from_row(row) for row in rows]

    def get(self, channel_id: str) -> Channel | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT id, type, name, enabled, status, config_json, created_at, updated_at FROM channels WHERE id = ?",
                (channel_id,),
            ).fetchone()
        return self._channel_from_row(row) if row else None

    def create(self, channel_id: str, channel_type: str, name: str, enabled: bool = False, config: dict | None = None) -> Channel:
        channel_id = channel_id.strip().lower()
        if channel_type not in CHANNEL_TYPES:
            raise ValueError("Type channel invalide.")
        if self.get(channel_id):
            raise FileExistsError("Channel deja existant.")
        clean_config = config or {}
        status = configured_status(channel_type, clean_config) if enabled else "disabled"
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO channels(id, type, name, enabled, status, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (channel_id, channel_type, name.strip() or channel_id, int(enabled), status, json.dumps(clean_config, ensure_ascii=False), now, now),
            )
        return self.get(channel_id)

    def update(self, channel_id: str, name: str | None = None, enabled: bool | None = None, config: dict | None = None) -> Channel | None:
        current = self.get(channel_id)
        if current is None:
            return None
        next_config = current.config
        if config is not None:
            next_config.update(config)
        next_enabled = current.enabled if enabled is None else enabled
        status = configured_status(current.type, next_config) if next_enabled else "disabled"
        if current.type in {"telegram", "discord"} and next_enabled and not next_config.get("bot_token"):
            status = "not_configured"
            next_enabled = False
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE channels SET name = ?, enabled = ?, status = ?, config_json = ?, updated_at = ? WHERE id = ?",
                (name.strip() if name is not None and name.strip() else current.name, int(next_enabled), status, json.dumps(next_config, ensure_ascii=False), now, channel_id),
            )
        return self.get(channel_id)

    def delete(self, channel_id: str) -> bool:
        if channel_id in {"web", "cli"}:
            raise ValueError("Les channels web et cli ne peuvent pas etre supprimes.")
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        return result.rowcount > 0

    def test(self, channel_id: str) -> dict:
        channel = self.get(channel_id)
        if channel is None:
            raise ValueError("Channel introuvable.")
        adapter = ADAPTERS[channel.type]
        result = adapter.test(channel.config)
        self.update(channel.id, enabled=channel.enabled, config={})
        return {"ok": result.ok, "status": result.status, "message": result.message, "channel": channel.as_api()}

    def get_or_create_account(
        self,
        channel_id: str,
        external_account_id: str,
        display_name: str = "",
        route_to_agent: str = "",
        metadata: dict | None = None,
    ) -> ChannelAccount:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, channel_id, external_account_id, display_name, route_to_agent, metadata_json
                FROM channel_accounts
                WHERE channel_id = ? AND external_account_id = ?
                """,
                (channel_id, external_account_id),
            ).fetchone()
            if row:
                return self._account_from_row(row)
            account = ChannelAccount(
                id=uuid4().hex,
                channel_id=channel_id,
                external_account_id=external_account_id,
                display_name=display_name,
                route_to_agent=route_to_agent,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            conn.execute(
                """
                INSERT INTO channel_accounts(id, channel_id, external_account_id, display_name, route_to_agent, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account.id, account.channel_id, account.external_account_id, account.display_name, account.route_to_agent, account.metadata_json),
            )
        return account

    def session_for_incoming(self, channel: Channel, external_account_id: str, display_name: str = "", route_to_agent: str = "") -> tuple[str, ChannelAccount]:
        account = self.get_or_create_account(channel.id, external_account_id, display_name=display_name, route_to_agent=route_to_agent)
        metadata = account.metadata
        session_id = str(metadata.get("session_id") or "")
        sessions = SessionsStore(self.config)
        if session_id and sessions.get_session(session_id):
            return session_id, account
        session = sessions.create_session(f"{channel.name}: {display_name or external_account_id}")
        if route_to_agent:
            sessions.set_agent_profile(session.id, route_to_agent)
        metadata["session_id"] = session.id
        metadata["channel_id"] = channel.id
        metadata["external_channel"] = channel.external
        self.update_account_metadata(account.id, metadata)
        return session.id, self.get_account(account.id)

    def update_account_metadata(self, account_id: str, metadata: dict) -> None:
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE channel_accounts SET metadata_json = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), account_id),
            )

    def get_account(self, account_id: str) -> ChannelAccount:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT id, channel_id, external_account_id, display_name, route_to_agent, metadata_json FROM channel_accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        return self._account_from_row(row)

    def _channel_from_row(self, row) -> Channel:
        return Channel(row["id"], row["type"], row["name"], bool(row["enabled"]), row["status"], row["config_json"], row["created_at"], row["updated_at"])

    def _account_from_row(self, row) -> ChannelAccount:
        return ChannelAccount(row["id"], row["channel_id"], row["external_account_id"], row["display_name"], row["route_to_agent"], row["metadata_json"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
