from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
CONFIG_ENV_VAR = "OMEGA_CONFIG_PATH"

SECRET_NAMES = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "CUSTOM_OPENAI_API_KEY",
    "OMEGA_TELEGRAM_BOT_TOKEN",
    "OMEGA_DISCORD_BOT_TOKEN",
}


def default_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "app": {
            "name": "Omega Agent",
            "language": "fr",
            "open_browser": True,
            "ui_theme": "dark",
        },
        "gateway": {
            "host": "127.0.0.1",
            "port": 8765,
        },
        "workspace": {
            "path": "~/omega_workspace",
            "full_access": True,
            "require_approval": False,
            "require_approval_outside_workspace": True,
            "shell_full_access": True,
            "allow_delete": True,
            "allow_git_write": True,
        },
        "model": {
            "selection_enabled": True,
            "default": "codex/gpt-5.5",
            "fallback": None,
            "auth_cache_seconds": 300,
            "status_cache_seconds": 60,
        },
        "providers": {
            "codex": {
                "enabled": True,
                "auth": {"type": "codex_oauth"},
                "models": ["gpt-5.5"],
            },
            "openai_api": {
                "enabled": False,
                "auth": {"type": "secret_ref", "secret": "OPENAI_API_KEY"},
                "base_url": None,
                "models": [],
            },
            "openrouter": {
                "enabled": False,
                "auth": {"type": "secret_ref", "secret": "OPENROUTER_API_KEY"},
                "base_url": "https://openrouter.ai/api/v1",
                "models": [],
            },
            "ollama": {
                "enabled": False,
                "auth": {"type": "none"},
                "base_url": "http://127.0.0.1:11434",
                "models": [],
            },
            "anthropic": {
                "enabled": False,
                "auth": {"type": "secret_ref", "secret": "ANTHROPIC_API_KEY"},
                "models": [],
            },
            "gemini": {
                "enabled": False,
                "auth": {"type": "secret_ref", "secret": "GEMINI_API_KEY"},
                "models": [],
            },
            "custom_openai_compatible": {
                "enabled": False,
                "auth": {"type": "secret_ref", "secret": "CUSTOM_OPENAI_API_KEY"},
                "base_url": None,
                "models": [],
            },
        },
        "channels": {
            "enabled": True,
            "webhooks_enabled": True,
            "telegram": {"enabled": False, "token_secret": "OMEGA_TELEGRAM_BOT_TOKEN"},
            "discord": {"enabled": False, "token_secret": "OMEGA_DISCORD_BOT_TOKEN"},
        },
        "scheduler": {
            "enabled": False,
            "tick_seconds": 30,
        },
        "reasoning": {
            "stream": True,
            "detail": "minimal",
        },
        "performance": {
            "fast_mode": True,
            "streaming": True,
            "status_cache_seconds": 60,
            "max_history_messages": 20,
            "max_memory_results": 5,
            "max_skills_in_context": 5,
            "max_tool_descriptions": 20,
            "load_plugins_on_startup": True,
            "reload_plugins_per_message": False,
            "reload_skills_per_message": False,
        },
        "paths": {
            "skills_dir": "~/omega_skills",
            "plugins_dir": "~/omega_plugins",
            "db_path": "~/.omega/omega.db",
        },
    }


ENV_TO_CONFIG_PATH = {
    "OMEGA_OPEN_BROWSER": "app.open_browser",
    "OMEGA_UI_THEME": "app.ui_theme",
    "OMEGA_HOST": "gateway.host",
    "OMEGA_PORT": "gateway.port",
    "OMEGA_WORKSPACE": "workspace.path",
    "OMEGA_WORKSPACE_FULL_ACCESS": "workspace.full_access",
    "OMEGA_REQUIRE_APPROVAL": "workspace.require_approval",
    "OMEGA_REQUIRE_APPROVAL_OUTSIDE_WORKSPACE": "workspace.require_approval_outside_workspace",
    "OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE": "workspace.shell_full_access",
    "OMEGA_ALLOW_DELETE_IN_WORKSPACE": "workspace.allow_delete",
    "OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE": "workspace.allow_git_write",
    "OMEGA_DEFAULT_MODEL": "model.default",
    "OMEGA_FALLBACK_MODEL": "model.fallback",
    "OMEGA_MODEL_SELECTION_ENABLED": "model.selection_enabled",
    "OMEGA_MODEL_AUTH_CACHE_SECONDS": "model.auth_cache_seconds",
    "OMEGA_MODEL_STATUS_CACHE_SECONDS": "model.status_cache_seconds",
    "OMEGA_CHANNELS_ENABLED": "channels.enabled",
    "OMEGA_WEBHOOKS_ENABLED": "channels.webhooks_enabled",
    "OMEGA_TELEGRAM_ENABLED": "channels.telegram.enabled",
    "OMEGA_DISCORD_ENABLED": "channels.discord.enabled",
    "OMEGA_SCHEDULER_ENABLED": "scheduler.enabled",
    "OMEGA_SCHEDULER_TICK_SECONDS": "scheduler.tick_seconds",
    "OMEGA_REASONING_STREAM": "reasoning.stream",
    "OMEGA_REASONING_DETAIL": "reasoning.detail",
    "OMEGA_FAST_MODE": "performance.fast_mode",
    "OMEGA_STREAMING": "performance.streaming",
    "OMEGA_STATUS_CACHE_SECONDS": "performance.status_cache_seconds",
    "OMEGA_MAX_HISTORY_MESSAGES": "performance.max_history_messages",
    "OMEGA_MAX_MEMORY_RESULTS": "performance.max_memory_results",
    "OMEGA_MAX_SKILLS_IN_CONTEXT": "performance.max_skills_in_context",
    "OMEGA_MAX_TOOL_DESCRIPTIONS": "performance.max_tool_descriptions",
    "OMEGA_LOAD_PLUGINS_ON_STARTUP": "performance.load_plugins_on_startup",
    "OMEGA_RELOAD_PLUGINS_PER_MESSAGE": "performance.reload_plugins_per_message",
    "OMEGA_RELOAD_SKILLS_PER_MESSAGE": "performance.reload_skills_per_message",
    "OMEGA_SKILLS_DIR": "paths.skills_dir",
    "OMEGA_PLUGINS_DIR": "paths.plugins_dir",
    "OMEGA_DB_PATH": "paths.db_path",
    "OPENAI_BASE_URL": "providers.openai_api.base_url",
    "OPENROUTER_BASE_URL": "providers.openrouter.base_url",
    "OLLAMA_BASE_URL": "providers.ollama.base_url",
    "CUSTOM_OPENAI_BASE_URL": "providers.custom_openai_compatible.base_url",
}


def config_path() -> Path:
    configured = os.getenv(CONFIG_ENV_VAR, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".omega" / "config.json").resolve()


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    data = default_config()
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Configuration JSON invalide: {target}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("config.json doit contenir un objet JSON.")
        _deep_merge(data, loaded)
    return data


def save_config(config: dict[str, Any], path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(config)
    payload.setdefault("version", CONFIG_VERSION)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def ensure_default_config(path: Path | None = None) -> Path:
    target = path or config_path()
    if target.exists():
        return target
    return save_config(default_config(), target)


def get_config_value(path: str, config: dict[str, Any] | None = None, file_path: Path | None = None) -> Any:
    data = config if config is not None else load_config(file_path)
    current: Any = data
    for part in _split_path(path):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def set_config_value(path: str, value: Any, config: dict[str, Any] | None = None, file_path: Path | None = None) -> dict[str, Any]:
    data = copy.deepcopy(config) if config is not None else load_config(file_path)
    parts = _split_path(path)
    current = data
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise ValueError(f"Chemin non objet: {'.'.join(parts[:-1])}")
        current = next_value
    current[parts[-1]] = value
    if config is None:
        save_config(data, file_path)
    return data


def unset_config_value(path: str, config: dict[str, Any] | None = None, file_path: Path | None = None) -> dict[str, Any]:
    data = copy.deepcopy(config) if config is not None else load_config(file_path)
    parts = _split_path(path)
    current = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise KeyError(path)
    del current[parts[-1]]
    if config is None:
        save_config(data, file_path)
    return data


def migrate_env_to_config(env_path: Path | None = None, *, force: bool = False, path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    env_file = env_path or Path(".env")
    legacy_values = _read_env_file(env_file)
    data = load_config(target) if target.exists() else default_config()
    migrated: list[str] = []
    skipped: list[str] = []

    if "OMEGA_DEFAULT_MODEL" not in legacy_values and legacy_values.get("OMEGA_PROVIDER") and legacy_values.get("OMEGA_MODEL"):
        legacy_values["OMEGA_DEFAULT_MODEL"] = _legacy_model_ref(legacy_values["OMEGA_PROVIDER"], legacy_values["OMEGA_MODEL"])

    for env_name, config_key in ENV_TO_CONFIG_PATH.items():
        if env_name not in legacy_values:
            continue
        converted = _coerce_value(legacy_values[env_name])
        try:
            existing = get_config_value(config_key, data)
        except KeyError:
            existing = None
        default_existing = _get_default_or_none(config_key)
        if target.exists() and not force and existing != default_existing:
            skipped.append(env_name)
            continue
        data = set_config_value(config_key, converted, data)
        migrated.append(env_name)

    save_config(data, target)
    return {"path": str(target), "migrated": migrated, "skipped": skipped, "legacy_env_present": env_file.exists()}


def redact_config_for_display(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = copy.deepcopy(config if config is not None else load_config())
    for provider in data.get("providers", {}).values():
        if isinstance(provider, dict):
            auth = provider.get("auth")
            if isinstance(auth, dict) and auth.get("secret"):
                auth["configured"] = bool(os.getenv(str(auth["secret"]), "").strip())
    return _redact_local(data)


def expected_secret_status(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = config if config is not None else load_config()
    names = set(SECRET_NAMES)
    for provider in data.get("providers", {}).values():
        if isinstance(provider, dict):
            auth = provider.get("auth")
            if isinstance(auth, dict) and auth.get("secret"):
                names.add(str(auth["secret"]))
    return [{"name": name, "configured": bool(os.getenv(name, "").strip())} for name in sorted(names)]


def legacy_env_values(path: Path | None = None) -> dict[str, str]:
    return _read_env_file(path or Path(".env"))


def parse_cli_value(value: str) -> Any:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", ""}:
        return None
    try:
        return int(stripped)
    except ValueError:
        return stripped


def _split_path(path: str) -> list[str]:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("Chemin config vide.")
    return parts


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _coerce_value(value: str) -> Any:
    return parse_cli_value(value)


def _get_default_or_none(path: str) -> Any:
    try:
        return get_config_value(path, default_config())
    except KeyError:
        return None


def _legacy_model_ref(provider: str, model: str) -> str:
    provider = provider.strip().lower() or "codex"
    if provider == "openai":
        provider = "openai_api"
    model = model.strip() or "gpt-5.5"
    if "/" in model:
        return model
    return f"{provider}/{model}"


_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{8,}"),
]


def _redact_local(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_local(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_local(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value
