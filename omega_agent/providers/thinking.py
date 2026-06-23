from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


OMEGA_THINKING_LEVELS = ("off", "auto", "minimal", "low", "medium", "high", "max")


@dataclass(frozen=True)
class ThinkingProfile:
    model_ref: str
    provider: str
    supported: bool
    mode: str = "unsupported"
    levels: tuple[str, ...] = ()
    default: str = "off"
    api_mapping: dict[str, dict[str, Any]] = field(default_factory=dict)
    reason: str = ""
    limitations: tuple[str, ...] = ()
    minimum_max_tokens: dict[str, int] = field(default_factory=dict)

    def api_parameters(self, level: str) -> dict[str, Any]:
        return deepcopy(self.api_mapping.get(level, {}))


@dataclass(frozen=True)
class ResolvedThinking:
    model_ref: str
    requested_level: str
    effective_level: str
    source: str
    profile: ThinkingProfile
    api_parameters: dict[str, Any]


class ThinkingConfigurationError(ValueError):
    pass


def split_model_ref(model_ref: str) -> tuple[str, str]:
    value = str(model_ref or "").strip()
    if "/" not in value:
        return "", value
    provider, model = value.split("/", 1)
    return provider.strip().lower(), model.strip()


def _openai_gpt55_profile(model_ref: str, provider: str) -> ThinkingProfile:
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=True,
        mode="reasoning_effort",
        levels=("off", "auto", "low", "medium", "high", "max"),
        default="auto",
        api_mapping={
            "off": {"reasoning": {"effort": "none"}},
            "auto": {},
            "low": {"reasoning": {"effort": "low"}},
            "medium": {"reasoning": {"effort": "medium"}},
            "high": {"reasoning": {"effort": "high"}},
            "max": {"reasoning": {"effort": "xhigh"}},
        },
        limitations=(
            "Le niveau Omega max correspond à xhigh pour ce modèle.",
            "Le niveau auto laisse le provider appliquer son comportement par défaut.",
        ),
    )


def _gemini25_profile(model_ref: str, provider: str, model: str) -> ThinkingProfile:
    can_disable = "pro" not in model.lower()
    levels = ("off", "auto", "low", "medium", "high") if can_disable else ("auto", "low", "medium", "high")
    mappings: dict[str, dict[str, Any]] = {
        "auto": {"thinking_budget": -1},
        "low": {"thinking_budget": 1024},
        "medium": {"thinking_budget": 4096},
        "high": {"thinking_budget": 8192},
    }
    if can_disable:
        mappings["off"] = {"thinking_budget": 0}
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=True,
        mode="thinking_budget",
        levels=levels,
        default="auto",
        api_mapping=mappings,
        limitations=(
            ("Ce modèle ne permet pas de désactiver complètement le thinking.",)
            if not can_disable
            else ()
        ),
    )


def _gemini3_profile(model_ref: str, provider: str, model: str) -> ThinkingProfile:
    is_flash = "flash" in model.lower()
    levels = ("minimal", "low", "medium", "high") if is_flash else ("low", "high")
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=True,
        mode="thinking_level",
        levels=levels,
        default="high",
        api_mapping={level: {"thinking_level": level.upper()} for level in levels},
        limitations=("Les niveaux disponibles dépendent de la variante Gemini 3.",),
    )


def _anthropic_adaptive_profile(model_ref: str, provider: str) -> ThinkingProfile:
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=True,
        mode="adaptive_thinking",
        levels=("off", "auto", "low", "medium", "high", "max"),
        default="auto",
        api_mapping={
            "off": {},
            "auto": {"thinking": {"type": "adaptive"}},
            "low": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}},
            "medium": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}},
            "high": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
            "max": {"thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}},
        },
        limitations=("Adaptive thinking exige un modèle Claude 4.6 compatible.",),
    )


def _anthropic_budget_profile(model_ref: str, provider: str) -> ThinkingProfile:
    budgets = {"low": 1024, "medium": 4096, "high": 8192, "max": 16000}
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=True,
        mode="budget_tokens",
        levels=("off", "low", "medium", "high", "max"),
        default="off",
        api_mapping={
            "off": {},
            **{
                level: {"thinking": {"type": "enabled", "budget_tokens": budget}}
                for level, budget in budgets.items()
            },
        },
        limitations=("budget_tokens doit rester inférieur à max_tokens.",),
        minimum_max_tokens={level: budget + 1 for level, budget in budgets.items()},
    )


def _unsupported_profile(model_ref: str, provider: str, reason: str = "") -> ThinkingProfile:
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=False,
        reason=reason or "Ce modèle ne publie aucun contrôle thinking/reasoning connu.",
    )


def builtin_profile(model_ref: str) -> ThinkingProfile:
    provider, model = split_model_ref(model_ref)
    normalized_model = model.lower()

    if provider in {"openai", "openai_api"} and normalized_model == "gpt-5.5":
        return _openai_gpt55_profile(model_ref, provider)
    if provider == "openrouter" and normalized_model == "openai/gpt-5.5":
        return _openai_gpt55_profile(model_ref, provider)
    if provider in {"google", "gemini"} and normalized_model.startswith("gemini-2.5-"):
        return _gemini25_profile(model_ref, provider, model)
    if provider in {"google", "gemini"} and normalized_model.startswith("gemini-3-"):
        return _gemini3_profile(model_ref, provider, model)
    if provider == "anthropic" and (
        normalized_model.startswith("claude-opus-4-6")
        or normalized_model.startswith("claude-sonnet-4-6")
    ):
        return _anthropic_adaptive_profile(model_ref, provider)
    if provider == "anthropic" and any(
        family in normalized_model
        for family in ("claude-sonnet-4-5", "claude-sonnet-4.5", "claude-opus-4-5", "claude-opus-4.5")
    ):
        return _anthropic_budget_profile(model_ref, provider)
    if provider == "codex":
        return _unsupported_profile(
            model_ref,
            provider,
            "La version Codex CLI doit exposer explicitement un réglage de reasoning avant qu'Omega ne le transmette.",
        )
    if provider in {"ollama", "lmstudio"}:
        return _unsupported_profile(
            model_ref,
            provider,
            "Aucun paramètre thinking standard n'est supposé pour ce provider local. Un profil manuel est requis.",
        )
    if provider in {"openrouter", "openai-compatible", "openai_compatible"}:
        return _unsupported_profile(
            model_ref,
            provider,
            "Le pass-through reasoning est désactivé pour les modèles inconnus. Ajoutez un profil manuel vérifié.",
        )
    return _unsupported_profile(model_ref, provider)


def profile_from_config(model_ref: str, raw: dict[str, Any]) -> ThinkingProfile:
    provider, _ = split_model_ref(model_ref)
    levels = tuple(
        str(level).lower()
        for level in raw.get("levels", [])
        if str(level).lower() in OMEGA_THINKING_LEVELS
    )
    mapping = raw.get("api_mapping") if isinstance(raw.get("api_mapping"), dict) else {}
    minimums = raw.get("minimum_max_tokens") if isinstance(raw.get("minimum_max_tokens"), dict) else {}
    limitations_raw = raw.get("limitations", [])
    limitations = (
        (limitations_raw,)
        if isinstance(limitations_raw, str)
        else tuple(str(item) for item in limitations_raw)
    )
    default = str(raw.get("default", "off")).lower()
    supported = bool(raw.get("supported", False))
    if supported and default not in levels:
        default = levels[0] if levels else "off"
    return ThinkingProfile(
        model_ref=model_ref,
        provider=provider,
        supported=supported,
        mode=str(raw.get("mode", "unsupported")),
        levels=levels,
        default=default,
        api_mapping=deepcopy(mapping),
        reason=str(raw.get("reason", "")),
        limitations=limitations,
        minimum_max_tokens={str(key): int(value) for key, value in minimums.items()},
    )


class ThinkingMatrix:
    def __init__(self, config_data: dict[str, Any] | None = None):
        self.config_data = config_data or {}

    @property
    def settings(self) -> dict[str, Any]:
        value = self.config_data.get("thinking", {})
        return value if isinstance(value, dict) else {}

    def profile_for(self, model_ref: str) -> ThinkingProfile:
        profiles = self.settings.get("profiles", {})
        if isinstance(profiles, dict):
            raw = profiles.get(model_ref)
            if isinstance(raw, dict):
                return profile_from_config(model_ref, raw)
        return builtin_profile(model_ref)

    def configured_level(self, model_ref: str) -> tuple[str, str]:
        per_model = self.settings.get("per_model", {})
        if isinstance(per_model, dict) and model_ref in per_model:
            return str(per_model[model_ref]).lower(), "thinking.per_model"
        return str(self.settings.get("default", "auto")).lower(), "thinking.default"

    def validate_level(self, model_ref: str, level: str) -> ThinkingProfile:
        normalized = str(level).lower()
        if normalized not in OMEGA_THINKING_LEVELS:
            raise ThinkingConfigurationError(
                f"Niveau thinking inconnu '{level}'. Niveaux Omega : {', '.join(OMEGA_THINKING_LEVELS)}."
            )
        profile = self.profile_for(model_ref)
        if not profile.supported:
            if normalized in {"off", "auto"}:
                return profile
            if bool(self.settings.get("allow_unsupported_fallback", False)):
                return profile
            raise ThinkingConfigurationError(
                "Ce modèle ne supporte pas de contrôle thinking/reasoning connu."
            )
        if normalized == "auto":
            return profile
        if normalized not in profile.levels:
            raise ThinkingConfigurationError(
                f"Le modèle actuel ne supporte pas le niveau '{normalized}'. "
                f"Niveaux supportés pour {model_ref} : {', '.join(profile.levels)}."
            )
        return profile

    def resolve(self, model_ref: str, request_override: str | None = None) -> ResolvedThinking:
        if request_override is not None:
            requested = str(request_override).lower()
            source = "request"
        else:
            requested, source = self.configured_level(model_ref)
        profile = self.validate_level(model_ref, requested)
        if not profile.supported:
            return ResolvedThinking(
                model_ref=model_ref,
                requested_level=requested,
                effective_level="off",
                source=source,
                profile=profile,
                api_parameters={},
            )
        effective = requested
        if requested == "auto" and "auto" not in profile.api_mapping:
            effective = profile.default
        return ResolvedThinking(
            model_ref=model_ref,
            requested_level=requested,
            effective_level=effective,
            source=source,
            profile=profile,
            api_parameters=profile.api_parameters(effective),
        )


def deep_merge_payload(target: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge_payload(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def matrix_for_config(config: Any) -> ThinkingMatrix:
    from omega_agent.config_store import default_config, load_config

    config_path = getattr(config, "config_path", None)
    data = load_config(config_path) if config_path is not None else default_config()
    return ThinkingMatrix(data)


def thinking_status(matrix: ThinkingMatrix, model_ref: str) -> dict[str, Any]:
    profile = matrix.profile_for(model_ref)
    configured, source = matrix.configured_level(model_ref)
    payload: dict[str, Any] = {
        "supported": profile.supported,
        "levels": list(profile.levels),
        "configured_level": configured,
        "current_level": "off",
        "source": source,
        "mode": profile.mode,
        "reason": profile.reason,
        "limitations": list(profile.limitations),
    }
    try:
        resolved = matrix.resolve(model_ref)
    except ThinkingConfigurationError as exc:
        payload["valid"] = False
        payload["error"] = str(exc)
        return payload
    payload["valid"] = True
    payload["current_level"] = resolved.effective_level
    return payload


def save_thinking_level(config: Any, level: str, model_ref: str | None = None) -> dict[str, Any]:
    from omega_agent.config_store import load_config, save_config

    target_model = model_ref or str(getattr(config, "default_model_ref", "codex/gpt-5.5"))
    matrix = matrix_for_config(config)
    matrix.validate_level(target_model, level)
    config_path = getattr(config, "config_path", None)
    if config_path is None:
        raise ValueError("Aucun fichier config.json n'est configuré.")
    data = load_config(config_path)
    thinking = data.setdefault("thinking", {})
    if not isinstance(thinking, dict):
        thinking = {}
        data["thinking"] = thinking
    if model_ref:
        per_model = thinking.setdefault("per_model", {})
        if not isinstance(per_model, dict):
            per_model = {}
            thinking["per_model"] = per_model
        per_model[target_model] = str(level).lower()
    else:
        thinking["default"] = str(level).lower()
    save_config(data, config_path)
    return thinking_status(ThinkingMatrix(data), target_model)
