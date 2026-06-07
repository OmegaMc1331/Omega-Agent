from __future__ import annotations

from omega_agent.channels.base import ChannelAdapter, ChannelTestResult


class CliChannel(ChannelAdapter):
    type = "cli"

    def test(self, config: dict) -> ChannelTestResult:
        return ChannelTestResult(True, "active", "CLI Omega actif localement.")
