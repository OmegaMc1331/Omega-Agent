from __future__ import annotations

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderError, ProviderInfo


class GeminiProvider(BaseProvider):
    id = "gemini"
    name = "Gemini"
    auth_type = "env_api_key"

    def info(self) -> ProviderInfo:
        return ProviderInfo(id=self.id, name=self.name, description="Provider Gemini via GEMINI_API_KEY ou GOOGLE_API_KEY.", auth_type=self.auth_type, supports_streaming=True, supports_vision=True, supports_json=True, docs_url="https://ai.google.dev/gemini-api/docs", config_schema={"env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]})

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("gemini-2.5-pro", self.id, "gemini/gemini-2.5-pro", "Gemini 2.5 Pro", supports_streaming=True, supports_vision=True, supports_json=True, speed_tier="deep", cost_tier="high")]

    def check_auth(self) -> AuthStatus:
        return AuthStatus(self.id, "configured" if self.config.gemini_api_key or self.config.google_api_key else "missing", self.auth_type)

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        if not (self.config.gemini_api_key or self.config.google_api_key):
            raise ProviderAuthError("GEMINI_API_KEY ou GOOGLE_API_KEY manquante.")
        raise ProviderError("Gemini direct n'est pas encore active dans ce build.")
