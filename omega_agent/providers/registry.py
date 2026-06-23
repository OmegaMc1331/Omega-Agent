from __future__ import annotations

from copy import deepcopy
from typing import Type

from omega_agent.config import OmegaConfig
from omega_agent.config_store import default_config, load_config
from omega_agent.providers.anthropic_provider import AnthropicProvider
from omega_agent.providers.base import BaseProvider
from omega_agent.providers.codex_provider import CodexProvider
from omega_agent.providers.deepseek_provider import DeepSeekProvider
from omega_agent.providers.gemini_provider import GeminiProvider
from omega_agent.providers.google_provider import GoogleProvider
from omega_agent.providers.groq_provider import GroqProvider
from omega_agent.providers.lmstudio_provider import LMStudioProvider
from omega_agent.providers.mistral_provider import MistralProvider
from omega_agent.providers.ollama_provider import OllamaProvider
from omega_agent.providers.openai_api_provider import OpenAIAPIProvider
from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider
from omega_agent.providers.openai_provider import OpenAIProvider
from omega_agent.providers.openrouter_provider import OpenRouterProvider
from omega_agent.providers.vertex_provider import VertexProvider
from omega_agent.providers.xai_provider import XAIProvider


PROVIDER_TYPE_CLASSES: dict[str, Type[BaseProvider]] = {
    "codex": CodexProvider,
    "openai": OpenAIProvider,
    "openai-compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "gemini": GoogleProvider,
    "vertex": VertexProvider,
    "ollama": OllamaProvider,
}

PROVIDER_ID_CLASSES: dict[str, Type[BaseProvider]] = {
    "codex": CodexProvider,
    "openai": OpenAIProvider,
    "openai_api": OpenAIAPIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "gemini": GeminiProvider,
    "vertex": VertexProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "mistral": MistralProvider,
    "ollama": OllamaProvider,
    "lmstudio": LMStudioProvider,
    "deepseek": DeepSeekProvider,
    "xai": XAIProvider,
}

SUPPORTED_PROVIDER_TYPES = frozenset(PROVIDER_TYPE_CLASSES)


class ProviderRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self._items = _configured_items(config)

    def list(self) -> list[BaseProvider]:
        return [
            self._build(provider_id, settings)
            for provider_id, settings in sorted(self._items.items())
        ]

    def get(self, provider_id: str) -> BaseProvider | None:
        settings = self._items.get(provider_id)
        return self._build(provider_id, settings) if settings is not None else None

    def list_models(self):
        models = []
        for provider in self.list():
            models.extend(provider.list_models())
        return models

    def settings(self, provider_id: str) -> dict | None:
        value = self._items.get(provider_id)
        return deepcopy(value) if value is not None else None

    def _build(self, provider_id: str, settings: dict) -> BaseProvider:
        provider_type = str(settings.get("type") or provider_id).lower()
        provider_class = PROVIDER_ID_CLASSES.get(provider_id)
        if provider_class is None or provider_type not in {
            provider_class.provider_type,
            provider_class.id,
            "openai-compatible",
        }:
            provider_class = PROVIDER_TYPE_CLASSES.get(
                provider_type,
                OpenAICompatibleProvider
                if provider_type == "openai-compatible"
                else BaseProvider,
            )
        return provider_class(self.config, provider_id=provider_id, settings=settings)


def _configured_items(config: OmegaConfig) -> dict[str, dict]:
    if config.config_path is not None and config.config_path.exists():
        data = load_config(config.config_path)
    else:
        data = default_config()
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return {}
    items = providers.get("items")
    if not isinstance(items, dict):
        return {}
    return {
        str(provider_id): deepcopy(settings)
        for provider_id, settings in items.items()
        if isinstance(settings, dict)
    }
