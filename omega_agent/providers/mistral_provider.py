from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class MistralProvider(OpenAICompatibleProvider):
    id = "mistral"
    name = "Mistral API"
    default_api_key_env = "MISTRAL_API_KEY"
    default_base_url = "https://api.mistral.ai/v1"
    description = "API Mistral compatible OpenAI."
