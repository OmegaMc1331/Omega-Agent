from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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

    def ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / ".omega").mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "OmegaConfig":
        provider = os.getenv("OMEGA_PROVIDER", "codex").strip().lower()
        if provider not in VALID_PROVIDERS:
            raise ValueError(f"OMEGA_PROVIDER invalide: {provider}")
        legacy_model = os.getenv("OMEGA_MODEL", "gpt-5.5").strip() or "gpt-5.5"
        default_model_ref = os.getenv("OMEGA_DEFAULT_MODEL", "").strip() or _legacy_model_ref(provider, legacy_model)
        selected_provider, selected_model = _split_model_ref(default_model_ref, provider, legacy_model)
        fallback_model_ref = os.getenv("OMEGA_FALLBACK_MODEL", "").strip()
        model_selection_enabled = _parse_bool(os.getenv("OMEGA_MODEL_SELECTION_ENABLED", "true"))
        model_auth_cache_seconds = max(0, int(os.getenv("OMEGA_MODEL_AUTH_CACHE_SECONDS", "300").strip() or "300"))
        model_status_cache_seconds = max(0, int(os.getenv("OMEGA_MODEL_STATUS_CACHE_SECONDS", "60").strip() or "60"))
        workspace = Path(os.getenv("OMEGA_WORKSPACE", "~/omega_workspace").strip()).expanduser().resolve()
        home = Path.home().resolve()
        if workspace == home:
            raise PermissionError("OMEGA_WORKSPACE ne peut pas être le dossier HOME complet.")
        if workspace.parent == workspace:
            raise PermissionError("OMEGA_WORKSPACE ne peut pas être la racine du système de fichiers.")
        cfg = cls(
            model=selected_model,
            workspace=workspace,
            require_approval=_parse_bool(os.getenv("OMEGA_REQUIRE_APPROVAL", "true")),
            provider=selected_provider,
            host=os.getenv("OMEGA_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_parse_port(os.getenv("OMEGA_PORT", "8765")),
            open_browser=_parse_bool(os.getenv("OMEGA_OPEN_BROWSER", "true")),
            ui_theme=os.getenv("OMEGA_UI_THEME", "dark").strip() or "dark",
            skills_dir=Path(os.getenv("OMEGA_SKILLS_DIR", "~/omega_skills").strip()).expanduser().resolve(),
            plugins_dir=Path(os.getenv("OMEGA_PLUGINS_DIR", "~/omega_plugins").strip()).expanduser().resolve(),
            db_path=Path(os.getenv("OMEGA_DB_PATH", "~/.omega/omega.db").strip()).expanduser().resolve(),
            safe_mode=_parse_bool(os.getenv("OMEGA_SAFE_MODE", "true")),
            workspace_full_access=_parse_bool(os.getenv("OMEGA_WORKSPACE_FULL_ACCESS", "false")),
            require_approval_outside_workspace=_parse_bool(os.getenv("OMEGA_REQUIRE_APPROVAL_OUTSIDE_WORKSPACE", "true")),
            shell_full_access_in_workspace=_parse_bool(os.getenv("OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE", "false")),
            allow_delete_in_workspace=_parse_bool(os.getenv("OMEGA_ALLOW_DELETE_IN_WORKSPACE", "false")),
            allow_git_write_in_workspace=_parse_bool(os.getenv("OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE", "false")),
            channels_enabled=_parse_bool(os.getenv("OMEGA_CHANNELS_ENABLED", "true")),
            webhooks_enabled=_parse_bool(os.getenv("OMEGA_WEBHOOKS_ENABLED", "true")),
            telegram_enabled=_parse_bool(os.getenv("OMEGA_TELEGRAM_ENABLED", "false")),
            discord_enabled=_parse_bool(os.getenv("OMEGA_DISCORD_ENABLED", "false")),
            telegram_bot_token=os.getenv("OMEGA_TELEGRAM_BOT_TOKEN", "").strip(),
            discord_bot_token=os.getenv("OMEGA_DISCORD_BOT_TOKEN", "").strip(),
            scheduler_enabled=_parse_bool(os.getenv("OMEGA_SCHEDULER_ENABLED", "false")),
            scheduler_tick_seconds=max(5, int(os.getenv("OMEGA_SCHEDULER_TICK_SECONDS", "30").strip() or "30")),
            browser_enabled=_parse_bool(os.getenv("OMEGA_BROWSER_ENABLED", "false")),
            browser_headless=_parse_bool(os.getenv("OMEGA_BROWSER_HEADLESS", "false")),
            browser_profile_dir=Path(os.getenv("OMEGA_BROWSER_PROFILE_DIR", str(workspace / ".omega" / "browser-profile")).strip()).expanduser().resolve(),
            browser_require_approval=_parse_bool(os.getenv("OMEGA_BROWSER_REQUIRE_APPROVAL", "true")),
            desktop_enabled=_parse_bool(os.getenv("OMEGA_DESKTOP_ENABLED", "false")),
            desktop_require_approval=_parse_bool(os.getenv("OMEGA_DESKTOP_REQUIRE_APPROVAL", "true")),
            desktop_screenshots_dir=Path(os.getenv("OMEGA_DESKTOP_SCREENSHOTS_DIR", str(workspace / ".omega" / "screenshots")).strip()).expanduser().resolve(),
            reasoning_stream=_parse_bool(os.getenv("OMEGA_REASONING_STREAM", "true")),
            reasoning_detail=_parse_reasoning_detail(os.getenv("OMEGA_REASONING_DETAIL", "minimal")),
            fast_mode=_parse_bool(os.getenv("OMEGA_FAST_MODE", "true")),
            streaming=_parse_bool(os.getenv("OMEGA_STREAMING", "true")),
            perf_logging=_parse_bool(os.getenv("OMEGA_PERF_LOGGING", "true")),
            status_cache_seconds=max(0, int(os.getenv("OMEGA_STATUS_CACHE_SECONDS", "60").strip() or "60")),
            codex_auth_cache_seconds=max(0, int(os.getenv("OMEGA_CODEX_AUTH_CACHE_SECONDS", "300").strip() or "300")),
            max_history_messages=max(1, int(os.getenv("OMEGA_MAX_HISTORY_MESSAGES", "20").strip() or "20")),
            max_memory_results=max(0, int(os.getenv("OMEGA_MAX_MEMORY_RESULTS", "5").strip() or "5")),
            max_skills_in_context=max(0, int(os.getenv("OMEGA_MAX_SKILLS_IN_CONTEXT", "5").strip() or "5")),
            max_tool_descriptions=max(0, int(os.getenv("OMEGA_MAX_TOOL_DESCRIPTIONS", "20").strip() or "20")),
            reload_plugins_per_message=_parse_bool(os.getenv("OMEGA_RELOAD_PLUGINS_PER_MESSAGE", "false")),
            reload_skills_per_message=_parse_bool(os.getenv("OMEGA_RELOAD_SKILLS_PER_MESSAGE", "false")),
            load_plugins_on_startup=_parse_bool(os.getenv("OMEGA_LOAD_PLUGINS_ON_STARTUP", "true")),
            codex_mode=os.getenv("OMEGA_CODEX_MODE", "exec").strip().lower() or "exec",
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
            openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip() or "https://openrouter.ai/api/v1",
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
            custom_openai_base_url=os.getenv("CUSTOM_OPENAI_BASE_URL", "").strip(),
            custom_openai_api_key=os.getenv("CUSTOM_OPENAI_API_KEY", "").strip(),
            custom_openai_model=os.getenv("CUSTOM_OPENAI_MODEL", "").strip(),
        )
        cfg.ensure_dirs()
        return cfg


def _parse_port(value: str) -> int:
    try:
        port = int(value.strip())
    except ValueError as exc:
        raise ValueError("OMEGA_PORT doit être un entier.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("OMEGA_PORT doit être entre 1 et 65535.")
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
    raise ValueError("Valeur booléenne invalide.")
