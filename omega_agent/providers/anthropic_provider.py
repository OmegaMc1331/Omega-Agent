from __future__ import annotations

import json
from typing import Any

from omega_agent.providers.base import (
    BaseProvider,
    CompletionResult,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderError,
    model_name_from_ref,
)
from omega_agent.providers.thinking import deep_merge_payload


class AnthropicProvider(BaseProvider):
    id = "anthropic"
    name = "Anthropic API"
    provider_type = "anthropic"
    auth_type = "env_api_key"
    default_api_key_env = "ANTHROPIC_API_KEY"
    default_base_url = "https://api.anthropic.com"
    default_model = "claude-sonnet-4-5"
    description = "API Messages Anthropic."
    capabilities = ProviderCapabilities(
        chat=True,
        streaming=True,
        tool_calling=True,
        vision=True,
        json_mode=True,
        reasoning=True,
        remote=True,
        api_key=True,
    )

    def validate_config(self) -> list[str]:
        errors = super().validate_config()
        if not self.base_url:
            errors.append("base_url manquante.")
        return errors

    def chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> CompletionResult:
        if not self._api_key():
            raise ProviderAuthError(
                f"Variable d'environnement manquante : {self.api_key_env}"
            )
        system_parts = [
            str(item.get("content") or "")
            for item in history
            if item.get("role") == "system"
        ]
        messages = [
            {"role": item["role"], "content": item.get("content", "")}
            for item in history
            if item.get("role") in {"user", "assistant"}
        ]
        messages.append({"role": "user", "content": user_input})
        request_payload = {
            "model": model_name_from_ref(self.provider_id, model_ref),
            "max_tokens": int(self.settings.get("max_tokens") or 4096),
            "messages": messages,
        }
        if thinking:
            budget = thinking.get("thinking", {}).get("budget_tokens")
            if budget is not None and int(budget) >= int(request_payload["max_tokens"]):
                raise ProviderError(
                    f"{self.provider_id}: budget_tokens doit être inférieur à max_tokens "
                    f"({request_payload['max_tokens']})."
                )
            deep_merge_payload(request_payload, thinking)
        if system_parts:
            request_payload["system"] = "\n\n".join(system_parts)
        if tools:
            request_payload["tools"] = [
                {
                    "name": str(tool.get("function", {}).get("name") or ""),
                    "description": str(
                        tool.get("function", {}).get("description") or ""
                    ),
                    "input_schema": dict(
                        tool.get("function", {}).get("parameters") or {}
                    ),
                }
                for tool in tools
                if tool.get("function", {}).get("name")
            ]
        payload = self._request_json(
            "POST",
            f"{self.base_url}/v1/messages",
            payload=request_payload,
            headers={
                "x-api-key": self._api_key(),
                "anthropic-version": "2023-06-01",
            },
            timeout=60,
        )
        content_rows = payload.get("content")
        if not isinstance(content_rows, list):
            raise ProviderError(f"{self.provider_id}: réponse sans contenu.")
        actions = [
            {
                "tool": str(item.get("name")),
                "arguments": dict(item.get("input") or {}),
            }
            for item in content_rows
            if isinstance(item, dict)
            and item.get("type") == "tool_use"
            and item.get("name")
        ]
        content = "".join(
            str(item.get("text") or "")
            for item in content_rows
            if isinstance(item, dict) and item.get("type") == "text"
        )
        if actions:
            content = json.dumps({"omega_actions": actions}, ensure_ascii=False)
        if not content:
            raise ProviderError(f"{self.provider_id}: réponse sans contenu texte.")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return CompletionResult(
            content,
            input_tokens=_int_or_none(usage.get("input_tokens")),
            output_tokens=_int_or_none(usage.get("output_tokens")),
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
