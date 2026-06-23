from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    id = "deepseek"
    name = "DeepSeek API"
    default_api_key_env = "DEEPSEEK_API_KEY"
    default_base_url = "https://api.deepseek.com"
    default_model = "deepseek-chat"
    description = "API DeepSeek compatible OpenAI."
