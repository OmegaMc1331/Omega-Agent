from __future__ import annotations

from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderError, ProviderInfo


class AnthropicProvider(BaseProvider):
    id = "anthropic"
    name = "Anthropic"
    auth_type = "env_api_key"

    def info(self) -> ProviderInfo:
        return ProviderInfo(id=self.id, name=self.name, description="Provider Anthropic via ANTHROPIC_API_KEY.", auth_type=self.auth_type, supports_streaming=True, supports_vision=True, supports_json=True, supports_reasoning=True, docs_url="https://docs.anthropic.com", config_schema={"env": ["ANTHROPIC_API_KEY"]})

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("anthropic-claude-sonnet-4.5", self.id, "anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5", supports_streaming=True, supports_vision=True, supports_json=True, supports_reasoning=True, speed_tier="deep", cost_tier="high")]

    def check_auth(self) -> AuthStatus:
        return AuthStatus(self.id, "configured" if self.config.anthropic_api_key else "missing", self.auth_type)

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        if not self.config.anthropic_api_key:
            raise ProviderAuthError("ANTHROPIC_API_KEY manquante.")
        raise ProviderError("Anthropic direct n'est pas encore active dans ce build.")
