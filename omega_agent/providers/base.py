from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlsplit, urlunsplit

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact, redact_text

AuthStatusValue = Literal["configured", "missing", "invalid", "unknown"]


@dataclass(frozen=True)
class ProviderCapabilities:
    chat: bool = True
    streaming: bool = False
    tool_calling: bool = False
    vision: bool = False
    json_mode: bool = False
    reasoning: bool = False
    local: bool = False
    remote: bool = True
    oauth: bool = False
    api_key: bool = False
    openai_compatible: bool = False

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    auth_type: str
    provider_type: str = ""
    base_url: str = ""
    default_model: str = ""
    enabled: bool = True
    status: str = "unknown"
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json: bool = False
    supports_reasoning: bool = False
    supports_local: bool = False
    docs_url: str = ""
    config_schema: dict = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider_id: str
    ref: str
    display_name: str
    description: str = ""
    context_window: int = 0
    max_output_tokens: int = 0
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json: bool = False
    supports_reasoning: bool = False
    supports_local: bool = False
    recommended_for: list[str] = field(default_factory=list)
    speed_tier: str = "balanced"
    cost_tier: str = "unknown"
    enabled: bool = True
    available: bool = True
    metadata: dict = field(default_factory=dict)

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class AuthStatus:
    provider_id: str
    status: AuthStatusValue
    auth_method: str
    metadata: dict = field(default_factory=dict)

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class ProviderTestResult:
    provider_id: str
    ok: bool
    status: str
    message: str
    metadata: dict = field(default_factory=dict)

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class CompletionResult:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    pass


class ProviderAuthError(ProviderError):
    pass


class BaseProvider:
    id = ""
    name = ""
    provider_type = ""
    auth_type = "none"
    default_api_key_env = ""
    default_base_url = ""
    default_model = ""
    description = ""
    docs_url = ""
    capabilities = ProviderCapabilities()

    def __init__(
        self,
        config: OmegaConfig,
        provider_id: str | None = None,
        settings: dict[str, Any] | None = None,
    ):
        self.config = config
        self.provider_id = provider_id or self.id
        self.settings = dict(settings or {})

    @property
    def display_name(self) -> str:
        return str(self.settings.get("display_name") or self.name or self.provider_id)

    @property
    def configured_type(self) -> str:
        return str(self.settings.get("type") or self.provider_type or self.provider_id)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled", True))

    @property
    def base_url(self) -> str:
        return str(self.settings.get("base_url") or self.default_base_url or "").rstrip("/")

    @property
    def configured_default_model(self) -> str:
        return str(self.settings.get("default_model") or self.default_model or "")

    @property
    def api_key_env(self) -> str:
        return str(self.settings.get("api_key_env") or self.default_api_key_env or "")

    def info(self) -> ProviderInfo:
        capabilities = self.capabilities.as_dict()
        return ProviderInfo(
            id=self.provider_id,
            name=self.display_name,
            description=self.description,
            auth_type=self.effective_auth_type(),
            provider_type=self.configured_type,
            base_url=_redact_url_credentials(self.base_url),
            default_model=self.configured_default_model,
            enabled=self.enabled,
            supports_streaming=capabilities["streaming"],
            supports_tools=capabilities["tool_calling"],
            supports_vision=capabilities["vision"],
            supports_json=capabilities["json_mode"],
            supports_reasoning=capabilities["reasoning"],
            supports_local=capabilities["local"],
            docs_url=self.docs_url,
            config_schema={
                "api_key_env": self.api_key_env,
                "base_url_configured": bool(self.base_url),
                "manual_models": list(self._configured_model_names()),
            },
            capabilities=capabilities,
        )

    def effective_auth_type(self) -> str:
        auth = self.settings.get("auth", self.auth_type)
        if isinstance(auth, dict):
            auth = auth.get("type", self.auth_type)
        auth = str(auth or self.auth_type)
        if auth in {"secret_ref", "env_api_key", "api_key"}:
            return "env_api_key"
        if auth in {"codex_oauth", "oauth"}:
            return "oauth"
        return auth

    def list_models(self) -> list[ModelInfo]:
        return [self._model_info(name) for name in self._configured_model_names()]

    def discover_models(self) -> list[ModelInfo]:
        return self.list_models()

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if self.effective_auth_type() == "env_api_key" and not self.api_key_env:
            errors.append("api_key_env manquant.")
        return errors

    def check_auth(self) -> AuthStatus:
        if self.effective_auth_type() == "env_api_key" and not self._api_key():
            return AuthStatus(
                self.provider_id,
                "missing",
                self.effective_auth_type(),
                {"api_key_env": self.api_key_env},
            )
        errors = self.validate_config()
        if errors:
            return AuthStatus(
                self.provider_id,
                "invalid",
                self.effective_auth_type(),
                {"message": " ".join(errors)},
            )
        if self.effective_auth_type() == "env_api_key":
            return AuthStatus(
                self.provider_id,
                "configured",
                self.effective_auth_type(),
                {"api_key_env": self.api_key_env},
            )
        return AuthStatus(self.provider_id, "configured", self.effective_auth_type())

    def test_connection(self) -> ProviderTestResult:
        status = self.check_auth()
        if status.status != "configured":
            message = status.metadata.get("message") or (
                f"Variable d'environnement manquante : {self.api_key_env}"
                if self.api_key_env
                else "Configuration provider invalide."
            )
            return ProviderTestResult(self.provider_id, False, status.status, str(message))
        return ProviderTestResult(
            self.provider_id,
            True,
            "configured",
            "Configuration provider valide.",
        )

    def chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        raise ProviderError(f"Provider {self.provider_id} ne supporte pas encore chat().")

    async def stream_chat(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
        *,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        result = await asyncio.to_thread(
            self.chat,
            model_ref,
            history,
            user_input,
            tools=tools,
        )
        yield result.content

    def complete(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
    ) -> CompletionResult:
        return self.chat(model_ref, history, user_input)

    async def stream(
        self,
        model_ref: str,
        history: list[dict[str, str]],
        user_input: str,
    ) -> AsyncIterator[str]:
        async for chunk in self.stream_chat(model_ref, history, user_input):
            yield chunk

    def supports_tools(self) -> bool:
        return self.capabilities.tool_calling

    def supports_streaming(self) -> bool:
        return self.capabilities.streaming

    def supports_model(self, model_ref: str) -> bool:
        provider_id, _ = split_model_ref(model_ref)
        return provider_id == self.provider_id

    def _api_key(self) -> str:
        if not self.api_key_env:
            return ""
        value = os.getenv(self.api_key_env, "").strip()
        if value:
            return value
        legacy_attributes = {
            "OPENAI_API_KEY": "openai_api_key",
            "OPENROUTER_API_KEY": "openrouter_api_key",
            "ANTHROPIC_API_KEY": "anthropic_api_key",
            "GEMINI_API_KEY": "gemini_api_key",
            "GOOGLE_API_KEY": "google_api_key",
            "CUSTOM_OPENAI_API_KEY": "custom_openai_api_key",
        }
        attribute = legacy_attributes.get(self.api_key_env)
        return str(getattr(self.config, attribute, "") or "").strip() if attribute else ""

    def _configured_model_names(self) -> list[str]:
        values = self.settings.get("models")
        models = [str(value).strip() for value in values] if isinstance(values, list) else []
        if self.configured_default_model and self.configured_default_model not in models:
            models.insert(0, self.configured_default_model)
        return [value for value in dict.fromkeys(models) if value]

    def _model_info(self, model_name: str, **metadata: Any) -> ModelInfo:
        caps = self.capabilities
        return ModelInfo(
            id=f"{self.provider_id}-{_safe_id(model_name)}",
            provider_id=self.provider_id,
            ref=f"{self.provider_id}/{model_name}",
            display_name=model_name,
            supports_streaming=caps.streaming,
            supports_tools=caps.tool_calling,
            supports_vision=caps.vision,
            supports_json=caps.json_mode,
            supports_reasoning=caps.reasoning,
            supports_local=caps.local,
            cost_tier="free" if caps.local else "unknown",
            metadata=metadata,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15,
    ) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                f"{self.provider_id}: HTTP {exc.code} sur {method} "
                f"{_redact_url_credentials(url)}."
            ) from exc
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise ProviderError(
                f"{self.provider_id}: connexion impossible sur {method} "
                f"{_redact_url_credentials(url)}: {redact_text(str(exc))}"
            ) from exc
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.provider_id}: réponse JSON invalide.") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"{self.provider_id}: réponse JSON inattendue.")
        return value


def model_name_from_ref(provider_id: str, model_ref: str) -> str:
    prefix = f"{provider_id}/"
    return model_ref[len(prefix) :] if model_ref.startswith(prefix) else model_ref


def split_model_ref(model_ref: str) -> tuple[str, str]:
    provider_id, separator, model_name = str(model_ref or "").partition("/")
    if not separator or not provider_id or not model_name:
        raise ValueError("Référence modèle invalide. Format attendu : provider/model.")
    return provider_id, model_name


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _redact_url_credentials(value: str) -> str:
    if "://" not in value:
        return value
    parsed = urlsplit(value)
    if parsed.username is None and parsed.password is None:
        return value
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit(
        (parsed.scheme, f"[REDACTED]@{hostname}", parsed.path, parsed.query, parsed.fragment)
    )
