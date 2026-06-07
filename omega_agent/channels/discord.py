from __future__ import annotations

from omega_agent.channels.base import ChannelAdapter, ChannelTestResult


class DiscordChannel(ChannelAdapter):
    type = "discord"

    def test(self, config: dict) -> ChannelTestResult:
        if not config.get("bot_token"):
            return ChannelTestResult(False, "not_configured", "Discord non configure: token absent.")
        return ChannelTestResult(True, "configured", "Discord configure, envoi reel non active en v0.")
