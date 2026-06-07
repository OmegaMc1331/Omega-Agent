from __future__ import annotations

from dataclasses import dataclass

EXTERNAL_CHANNEL_TYPES = {"webhook", "telegram", "discord"}


@dataclass(frozen=True)
class ChannelTestResult:
    ok: bool
    status: str
    message: str


class ChannelAdapter:
    type = "base"

    def test(self, config: dict) -> ChannelTestResult:
        return ChannelTestResult(True, "configured", "Channel disponible.")

    def is_external(self) -> bool:
        return self.type in EXTERNAL_CHANNEL_TYPES


def configured_status(channel_type: str, config: dict) -> str:
    if channel_type in {"web", "cli"}:
        return "active"
    if channel_type == "webhook":
        return "active" if config.get("enabled", True) else "disabled"
    if channel_type in {"telegram", "discord"}:
        return "configured" if config.get("bot_token") else "not_configured"
    return "disabled"
