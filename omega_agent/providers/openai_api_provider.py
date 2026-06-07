from __future__ import annotations

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderError, ProviderInfo


class OpenAIAPIProvider(BaseProvider):
    id = "openai_api"
    name = "OpenAI API"
    auth_type = "env_api_key"

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            description="Provider OpenAI API via OPENAI_API_KEY.",
            auth_type=self.auth_type,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json=True,
            supports_reasoning=True,
            docs_url="https://platform.openai.com/docs",
            config_schema={"env": ["OPENAI_API_KEY", "OPENAI_BASE_URL"]},
        )

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("openai-api-gpt-5.1", self.id, "openai_api/gpt-5.1", "GPT-5.1", supports_streaming=True, supports_tools=True, supports_json=True, supports_reasoning=True, speed_tier="deep", cost_tier="high"),
            ModelInfo("openai-api-gpt-5.1-mini", self.id, "openai_api/gpt-5.1-mini", "GPT-5.1 Mini", supports_streaming=True, supports_tools=True, supports_json=True, speed_tier="balanced", cost_tier="medium"),
        ]

    def check_auth(self) -> AuthStatus:
        return AuthStatus(self.id, "configured" if self.config.openai_api_key else "missing", self.auth_type, {"base_url_configured": bool(self.config.openai_base_url)})

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        if not self.config.openai_api_key:
            raise ProviderAuthError("OPENAI_API_KEY manquante.")
        raise ProviderError("OpenAI API direct n'est pas encore active dans ce build. Utilise Codex ou configure un provider compatible dans une version ulterieure.")
