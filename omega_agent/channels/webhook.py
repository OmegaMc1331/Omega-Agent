from __future__ import annotations

from omega_agent.channels.base import ChannelAdapter, ChannelTestResult


class WebhookChannel(ChannelAdapter):
    type = "webhook"

    def test(self, config: dict) -> ChannelTestResult:
        return ChannelTestResult(True, "active", "Webhook local pret a recevoir des POST.")
