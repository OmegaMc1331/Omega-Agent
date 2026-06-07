from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from omega_agent.config import OmegaConfig

AuthStatusValue = Literal["configured", "missing", "invalid", "unknown"]


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    auth_type: str
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

    def as_api(self) -> dict:
        return asdict(self)


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
        return asdict(self)


@dataclass(frozen=True)
class AuthStatus:
    provider_id: str
    status: AuthStatusValue
    auth_method: str
    metadata: dict = field(default_factory=dict)

    def as_api(self) -> dict:
        return asdict(self)


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
    auth_type = "none"

    def __init__(self, config: OmegaConfig):
        self.config = config

    def info(self) -> ProviderInfo:
        return ProviderInfo(id=self.id, name=self.name, description="", auth_type=self.auth_type)

    def list_models(self) -> list[ModelInfo]:
        return []

    def check_auth(self) -> AuthStatus:
        return AuthStatus(self.id, "unknown", self.auth_type)

    def complete(self, model_ref: str, history: list[dict[str, str]], user_input: str) -> CompletionResult:
        raise ProviderError(f"Provider {self.id} ne supporte pas encore complete().")

    async def stream(self, model_ref: str, history: list[dict[str, str]], user_input: str):
        result = self.complete(model_ref, history, user_input)
        yield result.content

    def supports_tools(self) -> bool:
        return self.info().supports_tools

    def supports_streaming(self) -> bool:
        return self.info().supports_streaming

    def supports_model(self, model_ref: str) -> bool:
        return any(model.ref == model_ref for model in self.list_models())


def model_name_from_ref(provider_id: str, model_ref: str) -> str:
    prefix = f"{provider_id}/"
    return model_ref[len(prefix) :] if model_ref.startswith(prefix) else model_ref
