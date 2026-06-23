from __future__ import annotations

from omega_agent.providers.openai_provider import OpenAIProvider


class OpenAIAPIProvider(OpenAIProvider):
    id = "openai_api"
    name = "OpenAI API (legacy id)"


__all__ = ["OpenAIAPIProvider"]
