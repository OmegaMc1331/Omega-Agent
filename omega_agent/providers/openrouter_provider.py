from __future__ import annotations

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderError, ProviderInfo


class OpenRouterProvider(BaseProvider):
    id = "openrouter"
    name = "OpenRouter"
    auth_type = "env_api_key"

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            description="Provider OpenRouter via OPENROUTER_API_KEY.",
            auth_type=self.auth_type,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supports_json=True,
            docs_url="https://openrouter.ai/docs",
            config_schema={"env": ["OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"]},
        )

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("openrouter-claude-sonnet-4.5", self.id, "openrouter/anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5", supports_streaming=True, supports_tools=True, supports_vision=True, supports_json=True, supports_reasoning=True, speed_tier="deep", cost_tier="high"),
            ModelInfo("openrouter-gpt-4.1", self.id, "openrouter/openai/gpt-4.1", "GPT-4.1 via OpenRouter", supports_streaming=True, supports_tools=True, supports_json=True, speed_tier="balanced", cost_tier="medium"),
        ]

    def check_auth(self) -> AuthStatus:
        return AuthStatus(self.id, "configured" if self.config.openrouter_api_key else "missing", self.auth_type, {"base_url_configured": bool(self.config.openrouter_base_url)})

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        if not self.config.openrouter_api_key:
            raise ProviderAuthError("OPENROUTER_API_KEY manquante.")
        raise ProviderError("OpenRouter direct n'est pas encore active dans ce build.")
