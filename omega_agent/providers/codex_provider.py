from __future__ import annotations

from dataclasses import replace
from typing import Any

from omega_agent.codex_backend import CODEX_LOGIN_HINT, codex_login_status_cached, run_codex_turn
from omega_agent.providers.base import (
    AuthStatus,
    BaseProvider,
    CompletionResult,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderTestResult,
    model_name_from_ref,
)

CODEX_DISCONNECTED_MESSAGE = "Codex n'est pas connecté. Lance : codex login"


class CodexProvider(BaseProvider):
    id = "codex"
    name = "Codex CLI / OAuth"
    provider_type = "codex"
    auth_type = "oauth"
    default_model = "gpt-5.5"
    description = "Exécution locale via Codex CLI et OAuth."
    capabilities = ProviderCapabilities(
        chat=True,
        reasoning=True,
        remote=True,
        oauth=True,
    )

    def check_auth(self) -> AuthStatus:
        connected, message = codex_login_status_cached(self.config.codex_auth_cache_seconds)
        return AuthStatus(
            self.provider_id,
            "configured" if connected else "missing",
            self.effective_auth_type(),
            {"message": message},
        )

    def test_connection(self) -> ProviderTestResult:
        status = self.check_auth()
        return ProviderTestResult(
            self.provider_id,
            status.status == "configured",
            status.status,
            str(status.metadata.get("message") or CODEX_DISCONNECTED_MESSAGE),
        )

    def chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> CompletionResult:
        model = model_name_from_ref(self.provider_id, model_ref)
        from omega_agent.runtime import agent as runtime_agent

        output = runtime_agent.run_codex_turn(
            replace(self.config, provider="codex", model=model),
            history,
            user_input,
        )
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
