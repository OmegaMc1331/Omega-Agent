from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from omega_agent.config_store import (
    config_path,
    load_config,
    save_config,
    set_config_value,
    unset_config_value,
)
from omega_agent.providers.catalog import BUILTIN_PROVIDER_NAMES
from omega_agent.providers.registry import SUPPORTED_PROVIDER_TYPES

PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ENV_NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def add_provider(
    name: str,
    *,
    provider_type: str,
    base_url: str | None = None,
    api_key_env: str | None = None,
    default_model: str | None = None,
    file_path: Path | None = None,
) -> dict:
    provider_id = validate_provider_id(name)
    normalized_type = provider_type.strip().lower()
    if normalized_type not in SUPPORTED_PROVIDER_TYPES:
        raise ValueError(
            "Type provider inconnu. Types supportés : "
            + ", ".join(sorted(SUPPORTED_PROVIDER_TYPES))
        )
    if base_url:
        validate_base_url(base_url)
    if api_key_env and not ENV_NAME_PATTERN.fullmatch(api_key_env):
        raise ValueError("api_key_env invalide.")
    if normalized_type in {"openai", "openai-compatible", "anthropic", "google", "gemini", "vertex"} and not api_key_env:
        raise ValueError("api_key_env est requis pour ce type de provider.")

    target = file_path or config_path()
    data = load_config(target)
    current = (
        data.get("providers", {})
        .get("items", {})
        .get(provider_id, {})
    )
    item = dict(current) if isinstance(current, dict) else {}
    item.update(
        {
            "type": normalized_type,
            "display_name": item.get("display_name") or provider_id,
            "enabled": True,
            "auth": "none" if not api_key_env else "api_key",
            "api_key_env": api_key_env or "",
            "base_url": (base_url or item.get("base_url") or "").rstrip("/"),
            "default_model": default_model or item.get("default_model") or "",
        }
    )
    models = list(item.get("models") or [])
    if default_model and default_model not in models:
        models.insert(0, default_model)
    item["models"] = models
    data = set_config_value(f"providers.items.{provider_id}", item, data)
    save_config(data, target)
    return item


def remove_provider(name: str, *, file_path: Path | None = None) -> None:
    provider_id = validate_provider_id(name)
    if provider_id in BUILTIN_PROVIDER_NAMES:
        raise ValueError(
            f"Le provider intégré {provider_id} ne peut pas être supprimé. Désactive-le."
        )
    target = file_path or config_path()
    data = load_config(target)
    items = data.get("providers", {}).get("items", {})
    if provider_id not in items:
        raise ValueError(f"Provider introuvable : {provider_id}")
    data = unset_config_value(f"providers.items.{provider_id}", data)
    providers = data.get("providers")
    if isinstance(providers, dict):
        providers.pop(provider_id, None)
        if providers.get("default") == provider_id:
            providers["default"] = "codex"
    save_config(data, target)


def set_provider_enabled(
    name: str,
    enabled: bool,
    *,
    file_path: Path | None = None,
) -> None:
    provider_id = validate_provider_id(name)
    target = file_path or config_path()
    data = load_config(target)
    items = data.get("providers", {}).get("items", {})
    if provider_id not in items:
        raise ValueError(f"Provider introuvable : {provider_id}")
    data = set_config_value(
        f"providers.items.{provider_id}.enabled",
        enabled,
        data,
    )
    save_config(data, target)


def set_default_provider(name: str, *, file_path: Path | None = None) -> None:
    provider_id = validate_provider_id(name)
    target = file_path or config_path()
    data = load_config(target)
    item = data.get("providers", {}).get("items", {}).get(provider_id)
    if not isinstance(item, dict):
        raise ValueError(f"Provider introuvable : {provider_id}")
    if not bool(item.get("enabled", True)):
        raise ValueError(f"Provider désactivé : {provider_id}")
    data = set_config_value("providers.default", provider_id, data)
    save_config(data, target)


def validate_provider_id(name: str) -> str:
    provider_id = name.strip().lower()
    if not PROVIDER_ID_PATTERN.fullmatch(provider_id):
        raise ValueError(
            "Nom provider invalide : utilise lettres minuscules, chiffres, tirets ou underscores."
        )
    return provider_id


def validate_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url doit être une URL HTTP ou HTTPS valide.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url ne doit pas contenir de credentials.")
