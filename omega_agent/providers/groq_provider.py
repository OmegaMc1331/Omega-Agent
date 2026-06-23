from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    name = "Groq"
    default_api_key_env = "GROQ_API_KEY"
    default_base_url = "https://api.groq.com/openai/v1"
    description = "API Groq compatible OpenAI."
