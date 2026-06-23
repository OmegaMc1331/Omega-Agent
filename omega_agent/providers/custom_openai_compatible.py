from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class CustomOpenAICompatibleProvider(OpenAICompatibleProvider):
    id = "custom_openai_compatible"
    name = "Custom OpenAI-compatible"
    default_api_key_env = "CUSTOM_OPENAI_API_KEY"


__all__ = ["CustomOpenAICompatibleProvider"]
