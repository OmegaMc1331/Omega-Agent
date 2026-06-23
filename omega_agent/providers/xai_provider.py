from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class XAIProvider(OpenAICompatibleProvider):
    id = "xai"
    name = "xAI API"
    default_api_key_env = "XAI_API_KEY"
    default_base_url = "https://api.x.ai/v1"
    description = "API xAI compatible OpenAI."
