from __future__ import annotations

import urllib.error
import urllib.request

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderError, ProviderInfo


class OllamaProvider(BaseProvider):
    id = "ollama"
    name = "Ollama"
    auth_type = "none"

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            description="Provider local Ollama.",
            auth_type=self.auth_type,
            supports_streaming=True,
            supports_local=True,
            docs_url="https://ollama.com",
            config_schema={"env": ["OLLAMA_BASE_URL"]},
        )

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("ollama-llama3.3", self.id, "ollama/llama3.3", "llama3.3", supports_streaming=True, supports_local=True, available=True, speed_tier="balanced", cost_tier="free")]

    def check_auth(self) -> AuthStatus:
        try:
            with urllib.request.urlopen(f"{self.config.ollama_base_url.rstrip('/')}/api/tags", timeout=1.5):
                return AuthStatus(self.id, "configured", self.auth_type, {"reachable": True, "local": True})
        except (OSError, urllib.error.URLError, TimeoutError):
            return AuthStatus(self.id, "missing", self.auth_type, {"reachable": False, "local": True})

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        raise ProviderError("Ollama complete n'est pas encore active dans ce build.")
