from __future__ import annotations

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderError, ProviderInfo


class CustomOpenAICompatibleProvider(BaseProvider):
    id = "custom_openai_compatible"
    name = "Custom OpenAI-compatible"
    auth_type = "env_api_key"

    def info(self) -> ProviderInfo:
        return ProviderInfo(id=self.id, name=self.name, description="Endpoint custom compatible OpenAI.", auth_type=self.auth_type, supports_streaming=True, supports_tools=True, supports_json=True, config_schema={"env": ["CUSTOM_OPENAI_BASE_URL", "CUSTOM_OPENAI_API_KEY", "CUSTOM_OPENAI_MODEL"]})

    def list_models(self) -> list[ModelInfo]:
        model = self.config.custom_openai_model or "custom-model"
        return [ModelInfo("custom-openai-compatible-default", self.id, f"custom_openai_compatible/{model}", model, supports_streaming=True, supports_tools=True, supports_json=True, available=bool(self.config.custom_openai_base_url))]

    def check_auth(self) -> AuthStatus:
        configured = bool(self.config.custom_openai_base_url and self.config.custom_openai_api_key)
        return AuthStatus(self.id, "configured" if configured else "missing", self.auth_type, {"base_url_configured": bool(self.config.custom_openai_base_url), "model_configured": bool(self.config.custom_openai_model)})

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        if not self.config.custom_openai_base_url or not self.config.custom_openai_api_key:
            raise ProviderAuthError("CUSTOM_OPENAI_BASE_URL ou CUSTOM_OPENAI_API_KEY manquant.")
        raise ProviderError("Custom OpenAI-compatible direct n'est pas encore active dans ce build.")
