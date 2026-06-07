from __future__ import annotations

from dataclasses import replace

from omega_agent.codex_backend import CODEX_LOGIN_HINT, codex_login_status_cached, run_codex_turn
from omega_agent.providers.base import AuthStatus, BaseProvider, CompletionResult, ModelInfo, ProviderAuthError, ProviderInfo, model_name_from_ref

CODEX_DISCONNECTED_MESSAGE = "Codex n'est pas connecté. Lance : codex login"


class CodexProvider(BaseProvider):
    id = "codex"
    name = "Codex OAuth"
    auth_type = "codex_oauth"

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            name=self.name,
            description="Provider Codex CLI avec OAuth ChatGPT officiel.",
            auth_type=self.auth_type,
            enabled=True,
            supports_streaming=False,
            supports_tools=False,
            supports_reasoning=True,
            docs_url="https://developers.openai.com/codex",
        )

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="codex-gpt-5.5",
                provider_id=self.id,
                ref="codex/gpt-5.5",
                display_name="GPT-5.5 via Codex",
                description="Modèle par défaut actuel via Codex OAuth.",
                context_window=200000,
                max_output_tokens=16000,
                supports_reasoning=True,
                recommended_for=["agent", "code", "deep"],
                speed_tier="deep",
                cost_tier="unknown",
            )
        ]

    def check_auth(self) -> AuthStatus:
        connected, message = codex_login_status_cached(self.config.codex_auth_cache_seconds)
        return AuthStatus(self.id, "configured" if connected else "missing", self.auth_type, {"message": message})

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        model = model_name_from_ref(self.id, model_ref)
        output = run_codex_turn(replace(self.config, provider="codex", model=model), history, user_input)
        if output == CODEX_LOGIN_HINT:
            raise ProviderAuthError(CODEX_DISCONNECTED_MESSAGE)
        return CompletionResult(output)


__all__ = [
    "CODEX_LOGIN_HINT",
    "CODEX_DISCONNECTED_MESSAGE",
    "CodexProvider",
    "codex_login_status_cached",
    "run_codex_turn",
]
