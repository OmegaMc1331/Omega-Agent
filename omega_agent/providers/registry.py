from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.providers.anthropic_provider import AnthropicProvider
from omega_agent.providers.base import BaseProvider
from omega_agent.providers.codex_provider import CodexProvider
from omega_agent.providers.custom_openai_compatible import CustomOpenAICompatibleProvider
from omega_agent.providers.gemini_provider import GeminiProvider
from omega_agent.providers.ollama_provider import OllamaProvider
from omega_agent.providers.openai_api_provider import OpenAIAPIProvider
from omega_agent.providers.openrouter_provider import OpenRouterProvider

PROVIDER_CLASSES = {
    "codex": CodexProvider,
    "openai_api": OpenAIAPIProvider,
    "openai": OpenAIAPIProvider,
    "openrouter": OpenRouterProvider,
    "ollama": OllamaProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "custom_openai_compatible": CustomOpenAICompatibleProvider,
}


class ProviderRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def list(self) -> list[BaseProvider]:
        return [cls(self.config) for provider_id, cls in PROVIDER_CLASSES.items() if provider_id != "openai"]

    def get(self, provider_id: str) -> BaseProvider | None:
        cls = PROVIDER_CLASSES.get(provider_id)
        return cls(self.config) if cls else None

    def list_models(self):
        models = []
        for provider in self.list():
            models.extend(provider.list_models())
        return models
