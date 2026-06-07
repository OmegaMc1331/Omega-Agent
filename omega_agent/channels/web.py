from __future__ import annotations

from omega_agent.channels.base import ChannelAdapter, ChannelTestResult


class WebChannel(ChannelAdapter):
    type = "web"

    def test(self, config: dict) -> ChannelTestResult:
        return ChannelTestResult(True, "active", "WebChat actif via Omega Gateway.")
