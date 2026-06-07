from __future__ import annotations

from omega_agent.channels.base import ChannelAdapter, ChannelTestResult


class TelegramChannel(ChannelAdapter):
    type = "telegram"

    def test(self, config: dict) -> ChannelTestResult:
        if not config.get("bot_token"):
            return ChannelTestResult(False, "not_configured", "Telegram non configure: token absent.")
        return ChannelTestResult(True, "configured", "Telegram configure, envoi reel non active en v0.")
