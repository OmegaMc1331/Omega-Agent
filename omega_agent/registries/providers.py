from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.providers.registry import ProviderRegistry


def list_providers(config: OmegaConfig | None = None) -> list[dict]:
    if config is None:
        return [
            {"id": "codex", "name": "Codex OAuth", "default_model": "gpt-5.5"},
            {"id": "openai_api", "name": "OpenAI API", "default_model": "gpt-5.1"},
            {"id": "ollama", "name": "Ollama", "default_model": "local"},
        ]
    return [provider.info().as_api() for provider in ProviderRegistry(config).list()]


__all__ = ["ProviderRegistry", "list_providers"]
