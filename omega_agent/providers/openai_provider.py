from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    id = "openai"
    name = "OpenAI API"
    provider_type = "openai"
    default_api_key_env = "OPENAI_API_KEY"
    default_base_url = "https://api.openai.com/v1"
    default_model = "gpt-5.1"
    description = "API OpenAI via une clé référencée par variable d'environnement."
