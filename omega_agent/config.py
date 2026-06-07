from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omega_agent.config_store import config_path as user_config_path
from omega_agent.config_store import get_config_value, legacy_env_values, load_config

VALID_PROVIDERS = {"codex", "openai", "openai_api", "openrouter", "ollama", "anthropic", "gemini", "custom_openai_compatible"}


@dataclass(frozen=True)
class OmegaConfig:
    model: str
    workspace: Path
    require_approval: bool
    provider: str = "codex"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    ui_theme: str = "dark"
    skills_dir: Path | None = None
    plugins_dir: Path | None = None
    db_path: Path | None = None
    safe_mode: bool = True
    workspace_full_access: bool = False
    require_approval_outside_workspace: bool = True
    shell_full_access_in_workspace: bool = False
    allow_delete_in_workspace: bool = False
    allow_git_write_in_workspace: bool = False
    channels_enabled: bool = True
    webhooks_enabled: bool = True
    telegram_enabled: bool = False
    discord_enabled: bool = False
    telegram_bot_token: str = ""
    discord_bot_token: str = ""
    scheduler_enabled: bool = False
    scheduler_tick_seconds: int = 30
    browser_enabled: bool = False
    browser_headless: bool = False
    browser_profile_dir: Path | None = None
    browser_require_approval: bool = True
    desktop_enabled: bool = False
    desktop_require_approval: bool = True
    desktop_screenshots_dir: Path | None = None
    reasoning_stream: bool = True
    reasoning_detail: str = "minimal"
    fast_mode: bool = True
    streaming: bool = True
    perf_logging: bool = True
    status_cache_seconds: int = 60
    codex_auth_cache_seconds: int = 300
    max_history_messages: int = 20
    max_memory_results: int = 5
    max_skills_in_context: int = 5
    max_tool_descriptions: int = 20
    reload_plugins_per_message: bool = False
    reload_skills_per_message: bool = False
    load_plugins_on_startup: bool = True
    codex_mode: str = "exec"
    default_model_ref: str = "codex/gpt-5.5"
    fallback_model_ref: str = ""
    model_selection_enabled: bool = True
    model_auth_cache_seconds: int = 300
    model_status_cache_seconds: int = 60
    omega_default_model: str = "codex/gpt-5.5"
    omega_fallback_model: str = ""
    omega_model_selection_enabled: bool = True
    omega_model_auth_cache_seconds: int = 300
    omega_model_status_cache_seconds: int = 60
    openai_api_key: str = ""
    openai_base_url: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    google_api_key: str = ""
    custom_openai_base_url: str = ""
    custom_openai_api_key: str = ""
    custom_openai_model: str = ""
    config_path: Path | None = None
    config_status: str = "defaults"
    model_config_source: str = "defaults"
    legacy_env_present: bool = False

    def ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / ".omega").mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "OmegaConfig":
        source = _ConfigSources()
        provider = source.get("OMEGA_PROVIDER", "codex").strip().lower()
        if provider not in VALID_PROVIDERS:
            raise ValueError(f"OMEGA_PROVIDER invalide: {provider}")

        legacy_model = source.get("OMEGA_MODEL", "gpt-5.5").strip() or "gpt-5.5"
        default_model_ref = source.get("OMEGA_DEFAULT_MODEL", "", "model.default").strip() or _legacy_model_ref(provider, legacy_model)
        selected_provider, selected_model = _split_model_ref(default_model_ref, provider, legacy_model)
        fallback_model_ref = source.get("OMEGA_FALLBACK_MODEL", "", "model.fallback").strip()
        model_selection_enabled = _parse_bool(source.get("OMEGA_MODEL_SELECTION_ENABLED", "true", "model.selection_enabled"))
        model_auth_cache_seconds = _parse_nonnegative_int(source.get("OMEGA_MODEL_AUTH_CACHE_SECONDS", "300", "model.auth_cache_seconds"), 300)
        model_status_cache_seconds = _parse_nonnegative_int(source.get("OMEGA_MODEL_STATUS_CACHE_SECONDS", "60", "model.status_cache_seconds"), 60)

        workspace = Path(source.get("OMEGA_WORKSPACE", "~/omega_workspace", "workspace.path").strip()).expanduser().resolve()
        _validate_workspace_root(workspace)

        cfg = cls(
            model=selected_model,
            workspace=workspace,
            require_approval=_parse_bool(source.get("OMEGA_REQUIRE_APPROVAL", "true", "workspace.require_approval")),
            provider=selected_provider,
            host=source.get("OMEGA_HOST", "127.0.0.1", "gateway.host").strip() or "127.0.0.1",
            port=_parse_port(source.get("OMEGA_PORT", "8765", "gateway.port")),
            open_browser=_parse_bool(source.get("OMEGA_OPEN_BROWSER", "true", "app.open_browser")),
            ui_theme=source.get("OMEGA_UI_THEME", "dark", "app.ui_theme").strip() or "dark",
            skills_dir=Path(source.get("OMEGA_SKILLS_DIR", "~/omega_skills", "paths.skills_dir").strip()).expanduser().resolve(),
            plugins_dir=Path(source.get("OMEGA_PLUGINS_DIR", "~/omega_plugins", "paths.plugins_dir").strip()).expanduser().resolve(),
            db_path=Path(source.get("OMEGA_DB_PATH", "~/.omega/omega.db", "paths.db_path").strip()).expanduser().resolve(),
            safe_mode=_parse_bool(source.get("OMEGA_SAFE_MODE", "true")),
            workspace_full_access=_parse_bool(source.get("OMEGA_WORKSPACE_FULL_ACCESS", "false", "workspace.full_access")),
            require_approval_outside_workspace=_parse_bool(source.get("OMEGA_REQUIRE_APPROVAL_OUTSIDE_WORKSPACE", "true", "workspace.require_approval_outside_workspace")),
            shell_full_access_in_workspace=_parse_bool(source.get("OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE", "false", "workspace.shell_full_access")),
            allow_delete_in_workspace=_parse_bool(source.get("OMEGA_ALLOW_DELETE_IN_WORKSPACE", "false", "workspace.allow_delete")),
            allow_git_write_in_workspace=_parse_bool(source.get("OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE", "false", "workspace.allow_git_write")),
            channels_enabled=_parse_bool(source.get("OMEGA_CHANNELS_ENABLED", "true", "channels.enabled")),
            webhooks_enabled=_parse_bool(source.get("OMEGA_WEBHOOKS_ENABLED", "true", "channels.webhooks_enabled")),
            telegram_enabled=_parse_bool(source.get("OMEGA_TELEGRAM_ENABLED", "false", "channels.telegram.enabled")),
            discord_enabled=_parse_bool(source.get("OMEGA_DISCORD_ENABLED", "false", "channels.discord.enabled")),
            telegram_bot_token=os.getenv("OMEGA_TELEGRAM_BOT_TOKEN", "").strip(),
            discord_bot_token=os.getenv("OMEGA_DISCORD_BOT_TOKEN", "").strip(),
            scheduler_enabled=_parse_bool(source.get("OMEGA_SCHEDULER_ENABLED", "false", "scheduler.enabled")),
            scheduler_tick_seconds=max(5, _parse_int(source.get("OMEGA_SCHEDULER_TICK_SECONDS", "30", "scheduler.tick_seconds"), 30)),
            browser_enabled=_parse_bool(source.get("OMEGA_BROWSER_ENABLED", "false")),
            browser_headless=_parse_bool(source.get("OMEGA_BROWSER_HEADLESS", "false")),
            browser_profile_dir=Path(source.get("OMEGA_BROWSER_PROFILE_DIR", str(workspace / ".omega" / "browser-profile")).strip()).expanduser().resolve(),
            browser_require_approval=_parse_bool(source.get("OMEGA_BROWSER_REQUIRE_APPROVAL", "true")),
            desktop_enabled=_parse_bool(source.get("OMEGA_DESKTOP_ENABLED", "false")),
            desktop_require_approval=_parse_bool(source.get("OMEGA_DESKTOP_REQUIRE_APPROVAL", "true")),
            desktop_screenshots_dir=Path(source.get("OMEGA_DESKTOP_SCREENSHOTS_DIR", str(workspace / ".omega" / "screenshots")).strip()).expanduser().resolve(),
            reasoning_stream=_parse_bool(source.get("OMEGA_REASONING_STREAM", "true", "reasoning.stream")),
            reasoning_detail=_parse_reasoning_detail(source.get("OMEGA_REASONING_DETAIL", "minimal", "reasoning.detail")),
            fast_mode=_parse_bool(source.get("OMEGA_FAST_MODE", "true", "performance.fast_mode")),
            streaming=_parse_bool(source.get("OMEGA_STREAMING", "true", "performance.streaming")),
            perf_logging=_parse_bool(source.get("OMEGA_PERF_LOGGING", "true")),
            status_cache_seconds=_parse_nonnegative_int(source.get("OMEGA_STATUS_CACHE_SECONDS", "60", "performance.status_cache_seconds"), 60),
            codex_auth_cache_seconds=_parse_nonnegative_int(source.get("OMEGA_CODEX_AUTH_CACHE_SECONDS", "300"), 300),
            max_history_messages=max(1, _parse_int(source.get("OMEGA_MAX_HISTORY_MESSAGES", "20", "performance.max_history_messages"), 20)),
            max_memory_results=_parse_nonnegative_int(source.get("OMEGA_MAX_MEMORY_RESULTS", "5", "performance.max_memory_results"), 5),
            max_skills_in_context=_parse_nonnegative_int(source.get("OMEGA_MAX_SKILLS_IN_CONTEXT", "5", "performance.max_skills_in_context"), 5),
            max_tool_descriptions=_parse_nonnegative_int(source.get("OMEGA_MAX_TOOL_DESCRIPTIONS", "20", "performance.max_tool_descriptions"), 20),
            reload_plugins_per_message=_parse_bool(source.get("OMEGA_RELOAD_PLUGINS_PER_MESSAGE", "false", "performance.reload_plugins_per_message")),
            reload_skills_per_message=_parse_bool(source.get("OMEGA_RELOAD_SKILLS_PER_MESSAGE", "false", "performance.reload_skills_per_message")),
            load_plugins_on_startup=_parse_bool(source.get("OMEGA_LOAD_PLUGINS_ON_STARTUP", "true", "performance.load_plugins_on_startup")),
            codex_mode=source.get("OMEGA_CODEX_MODE", "exec").strip().lower() or "exec",
            default_model_ref=default_model_ref,
            fallback_model_ref=fallback_model_ref,
            model_selection_enabled=model_selection_enabled,
            model_auth_cache_seconds=model_auth_cache_seconds,
            model_status_cache_seconds=model_status_cache_seconds,
            omega_default_model=default_model_ref,
            omega_fallback_model=fallback_model_ref,
            omega_model_selection_enabled=model_selection_enabled,
            omega_model_auth_cache_seconds=model_auth_cache_seconds,
            omega_model_status_cache_seconds=model_status_cache_seconds,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=source.get("OPENAI_BASE_URL", "", "providers.openai_api.base_url").strip(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_base_url=source.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", "providers.openrouter.base_url").strip() or "https://openrouter.ai/api/v1",
            ollama_base_url=source.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434", "providers.ollama.base_url").strip() or "http://127.0.0.1:11434",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
            custom_openai_base_url=source.get("CUSTOM_OPENAI_BASE_URL", "", "providers.custom_openai_compatible.base_url").strip(),
            custom_openai_api_key=os.getenv("CUSTOM_OPENAI_API_KEY", "").strip(),
            custom_openai_model=os.getenv("CUSTOM_OPENAI_MODEL", "").strip(),
            config_path=source.config_file,
            config_status=source.config_status,
            model_config_source=source.source_for("model.default"),
            legacy_env_present=source.legacy_env_present,
        )
        cfg.ensure_dirs()
        return cfg


class _ConfigSources:
    def __init__(self) -> None:
        self.config_file = user_config_path()
        self.config_exists = self.config_file.exists()
        self.config = load_config(self.config_file) if self.config_exists else {}
        self.legacy_env_path = Path(".env")
        # Runtime entrypoints call load_dotenv() for temporary legacy support.
        # Avoid reading cwd .env directly here, which would make tests and
        # embedded API clients depend on an unrelated repository-local file.
        self.legacy_env = legacy_env_values(self.legacy_env_path) if os.getenv("OMEGA_READ_LEGACY_ENV_FILE", "").lower() in {"1", "true", "yes"} else {}
        self.legacy_env_present = self.legacy_env_path.exists()
        self._source_by_path: dict[str, str] = {}
        self.config_status = "OK" if self.config_exists else "missing"

    def get(self, env_name: str, default: str, json_path: str | None = None) -> str:
        if self.config_exists and json_path:
            try:
                value = get_config_value(json_path, self.config)
                self._source_by_path[json_path] = "config.json"
                return _stringify_source_value(value)
            except KeyError:
                pass
        if env_name in os.environ:
            if json_path:
                self._source_by_path[json_path] = "environment"
            return os.getenv(env_name, default)
        if env_name in self.legacy_env:
            if json_path:
                self._source_by_path[json_path] = ".env legacy"
            return self.legacy_env[env_name]
        if json_path:
            self._source_by_path[json_path] = "defaults"
        return default

    def source_for(self, json_path: str) -> str:
        return self._source_by_path.get(json_path, "config.json" if self.config_exists else "defaults")


def _stringify_source_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _validate_workspace_root(workspace: Path) -> None:
    home = Path.home().resolve()
    if workspace == home:
        raise PermissionError("OMEGA_WORKSPACE ne peut pas etre le dossier HOME complet.")
    if workspace.parent == workspace:
        raise PermissionError("OMEGA_WORKSPACE ne peut pas etre la racine du systeme de fichiers.")


def _parse_port(value: str) -> int:
    try:
        port = int(value.strip())
    except ValueError as exc:
        raise ValueError("OMEGA_PORT doit etre un entier.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("OMEGA_PORT doit etre entre 1 et 65535.")
    return port


def _parse_reasoning_detail(value: str) -> str:
    detail = value.strip().lower() or "normal"
    if detail not in {"off", "minimal", "normal", "verbose"}:
        raise ValueError("OMEGA_REASONING_DETAIL doit valoir off, minimal, normal ou verbose.")
    return detail


def _legacy_model_ref(provider: str, model: str) -> str:
    model = model.strip() or "gpt-5.5"
    if "/" in model and model.split("/", 1)[0] in VALID_PROVIDERS:
        return model
    provider_id = "openai_api" if provider == "openai" else provider
    return f"{provider_id}/{model}"


def _split_model_ref(model_ref: str, fallback_provider: str, fallback_model: str) -> tuple[str, str]:
    parts = [part for part in model_ref.split("/") if part]
    if len(parts) < 2:
        return fallback_provider, fallback_model
    provider_id = parts[0]
    model = "/".join(parts[1:])
    if provider_id == "openai_api" and fallback_provider == "openai":
        return "openai", model
    return provider_id, model


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Valeur booleenne invalide.")


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value.strip() or str(default))
    except ValueError as exc:
        raise ValueError("Valeur entiere invalide.") from exc


def _parse_nonnegative_int(value: str, default: int) -> int:
    return max(0, _parse_int(value, default))
