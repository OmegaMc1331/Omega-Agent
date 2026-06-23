from __future__ import annotations

from omega_agent.providers.base import ProviderCapabilities
from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class LMStudioProvider(OpenAICompatibleProvider):
    id = "lmstudio"
    name = "LM Studio local"
    auth_type = "none"
    default_base_url = "http://127.0.0.1:1234/v1"
    description = "Serveur local LM Studio compatible OpenAI."
    capabilities = ProviderCapabilities(
        chat=True,
        streaming=True,
        tool_calling=True,
        vision=True,
        json_mode=True,
        reasoning=True,
        local=True,
        remote=False,
        openai_compatible=True,
    )

