from __future__ import annotations

import json

from omega_agent.providers.base import (
    BaseProvider,
    CompletionResult,
    ModelInfo,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderError,
    model_name_from_ref,
)


class GoogleProvider(BaseProvider):
    id = "google"
    name = "Google Gemini API"
    provider_type = "google"
    auth_type = "env_api_key"
    default_api_key_env = "GEMINI_API_KEY"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"
    default_model = "gemini-2.5-pro"
    description = "API Gemini generateContent."
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

    def discover_models(self) -> list[ModelInfo]:
        if not self._api_key():
            raise ProviderAuthError(
                f"Variable d'environnement manquante : {self.api_key_env}"
            )
        payload = self._request_json(
            "GET",
            f"{self.base_url}/models",
            headers={"x-goog-api-key": self._api_key()},
        )
        rows = payload.get("models")
        if not isinstance(rows, list):
            return self.list_models()
        models = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").removeprefix("models/")
            methods = row.get("supportedGenerationMethods") or []
            if name and "generateContent" in methods:
                models.append(self._model_info(name, discovered=True))
        return models or self.list_models()

    def chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
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
        contents = []
        for item in history:
            if item.get("role") not in {"user", "assistant"}:
                continue
            contents.append(
                {
                    "role": "model" if item["role"] == "assistant" else "user",
                    "parts": [{"text": str(item.get("content") or "")}],
                }
            )
        contents.append({"role": "user", "parts": [{"text": user_input}]})
        request_payload: dict = {"contents": contents}
        if system_parts:
            request_payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }
        if tools:
            request_payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": str(tool.get("function", {}).get("name") or ""),
                            "description": str(
                                tool.get("function", {}).get("description") or ""
                            ),
                            "parameters": dict(
                                tool.get("function", {}).get("parameters") or {}
                            ),
                        }
                        for tool in tools
                        if tool.get("function", {}).get("name")
                    ]
                }
            ]
        payload = self._request_json(
            "POST",
            f"{self.base_url}/models/{model_name_from_ref(self.provider_id, model_ref)}:generateContent",
            payload=request_payload,
            headers={"x-goog-api-key": self._api_key()},
            timeout=60,
        )
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderError(f"{self.provider_id}: réponse sans candidat.")
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        actions = []
        for part in parts:
            function_call = part.get("functionCall") if isinstance(part, dict) else None
            if isinstance(function_call, dict) and function_call.get("name"):
                actions.append(
                    {
                        "tool": str(function_call["name"]),
                        "arguments": dict(function_call.get("args") or {}),
                    }
                )
        text = "".join(
            str(part.get("text") or "") for part in parts if isinstance(part, dict)
        )
        if actions:
            text = json.dumps({"omega_actions": actions}, ensure_ascii=False)
        if not text:
            raise ProviderError(f"{self.provider_id}: réponse sans contenu texte.")
        usage = payload.get("usageMetadata") if isinstance(payload.get("usageMetadata"), dict) else {}
        return CompletionResult(
            text,
            input_tokens=_int_or_none(usage.get("promptTokenCount")),
            output_tokens=_int_or_none(usage.get("candidatesTokenCount")),
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
