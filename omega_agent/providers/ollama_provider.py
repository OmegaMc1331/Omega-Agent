from __future__ import annotations

from typing import Any

from omega_agent.providers.base import (
    BaseProvider,
    CompletionResult,
    ModelInfo,
    ProviderCapabilities,
    ProviderError,
    ProviderTestResult,
    model_name_from_ref,
)
from omega_agent.providers.thinking import deep_merge_payload


class OllamaProvider(BaseProvider):
    id = "ollama"
    name = "Ollama local"
    provider_type = "ollama"
    auth_type = "none"
    default_base_url = "http://127.0.0.1:11434"
    default_model = "llama3.1"
    description = "Serveur de modèles local Ollama."
    capabilities = ProviderCapabilities(
        chat=True,
        streaming=True,
        tool_calling=False,
        vision=True,
        json_mode=True,
        reasoning=True,
        local=True,
        remote=False,
    )

    def discover_models(self) -> list[ModelInfo]:
        payload = self._request_json("GET", f"{self.base_url}/api/tags", timeout=5)
        rows = payload.get("models")
        if not isinstance(rows, list):
            return self.list_models()
        models = [
            self._model_info(str(row.get("name")), discovered=True)
            for row in rows
            if isinstance(row, dict) and row.get("name")
        ]
        return models or self.list_models()

    def test_connection(self) -> ProviderTestResult:
        try:
            models = self.discover_models()
        except ProviderError as exc:
            return ProviderTestResult(
                self.provider_id,
                False,
                "unavailable",
                str(exc),
            )
        return ProviderTestResult(
            self.provider_id,
            True,
            "available",
            "Ollama accessible.",
            {"models_discovered": len(models)},
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
        messages = [dict(item) for item in history]
        messages.append({"role": "user", "content": user_input})
        request_payload = {
            "model": model_name_from_ref(self.provider_id, model_ref),
            "messages": messages,
            "stream": False,
        }
        if thinking:
            deep_merge_payload(request_payload, thinking)
        payload = self._request_json(
            "POST",
            f"{self.base_url}/api/chat",
            payload=request_payload,
            timeout=60,
        )
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderError(f"{self.provider_id}: réponse sans contenu texte.")
        return CompletionResult(
            content,
            input_tokens=_int_or_none(payload.get("prompt_eval_count")),
            output_tokens=_int_or_none(payload.get("eval_count")),
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
