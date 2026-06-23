from __future__ import annotations

from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider


class VertexProvider(OpenAICompatibleProvider):
    id = "vertex"
    name = "Google Vertex AI"
    provider_type = "vertex"
    default_api_key_env = "VERTEX_ACCESS_TOKEN"
    description = (
        "Endpoint Vertex AI configuré explicitement avec une base URL compatible OpenAI."
    )
