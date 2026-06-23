from __future__ import annotations

from typing import Any

from omega_agent.providers.base import (
    AuthStatus,
    BaseProvider,
    CompletionResult,
    ModelInfo,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderError,
    ProviderTestResult,
    model_name_from_ref,
)
from omega_agent.providers.thinking import deep_merge_payload


class OpenAICompatibleProvider(BaseProvider):
    id = "openai-compatible"
    name = "OpenAI-compatible"
    provider_type = "openai-compatible"
    auth_type = "env_api_key"
    description = "Endpoint HTTP compatible avec l'API Chat Completions OpenAI."
    capabilities = ProviderCapabilities(
        chat=True,
        streaming=True,
        tool_calling=True,
        vision=True,
        json_mode=True,
        reasoning=True,
        remote=True,
        api_key=True,
        openai_compatible=True,
    )

    def validate_config(self) -> list[str]:
        errors = super().validate_config()
        if not self.base_url:
            errors.append("base_url manquante.")
        return errors

    def discover_models(self) -> list[ModelInfo]:
        self._require_auth()
        payload = self._request_json(
            "GET",
            f"{self.base_url}/models",
            headers=self._headers(),
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ProviderError(f"{self.provider_id}: endpoint /models non supporté.")
        models = []
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                models.append(self._model_info(str(row["id"]), discovered=True))
        return models or self.list_models()

    def chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> CompletionResult:
        self._require_auth()
        model = model_name_from_ref(self.provider_id, model_ref)
        messages = [dict(item) for item in history]
        messages.append({"role": "user", "content": user_input})
        request_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools and self.capabilities.tool_calling:
            request_payload["tools"] = tools
        if thinking:
            deep_merge_payload(request_payload, thinking)
        payload = self._request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            payload=request_payload,
            headers=self._headers(),
            timeout=60,
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(f"{self.provider_id}: réponse sans choix.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        if isinstance(tool_calls, list) and tool_calls:
            actions = []
            for call in tool_calls:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict) or not function.get("name"):
                    continue
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = __import__("json").loads(arguments)
                    except ValueError:
                        arguments = {}
                actions.append(
                    {
                        "tool": str(function["name"]),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                )
            if actions:
                content = __import__("json").dumps(
                    {"omega_actions": actions},
                    ensure_ascii=False,
                )
        if isinstance(content, list):
            content = "".join(
                str(item.get("text") or "") for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str):
            raise ProviderError(f"{self.provider_id}: réponse sans contenu texte.")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return CompletionResult(
            content,
            input_tokens=_int_or_none(usage.get("prompt_tokens")),
            output_tokens=_int_or_none(usage.get("completion_tokens")),
            metadata={"provider_request_id": payload.get("id")},
        )

    def test_connection(self) -> ProviderTestResult:
        status = self.check_auth()
        if status.status != "configured":
            return super().test_connection()
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
            "Provider accessible.",
            {"models_discovered": len(models)},
        )

    def _require_auth(self) -> None:
        errors = self.validate_config()
        if errors:
            raise ProviderError(f"{self.provider_id}: {' '.join(errors)}")
        if self.effective_auth_type() == "env_api_key" and not self._api_key():
            raise ProviderAuthError(
                f"Variable d'environnement manquante : {self.api_key_env}"
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            str(name): str(value)
            for name, value in dict(self.settings.get("headers") or {}).items()
        }
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
