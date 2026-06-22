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
        "mobile": {
            "mode": "tailscale",
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
        "runtime": {
            "checkpoints": {"enabled": True},
            "snapshots": {
                "enabled": True,
                "max_file_size_mb": 10,
                "keep_days": 30,
            },
            "replay": {"enabled": True},
            "resume_interrupted_runs": False,
            "max_tool_iterations": 5,
            "max_actions_per_turn": 10,
            "max_run_seconds": 300,
            "dead_letter_enabled": True,
        },
        "capabilities": {
            "enabled": True,
            "max_in_context": 20,
            "mcp_enabled": False,
            "a2a_enabled": False,
            "untrusted_disabled_by_default": True,
            "usage_logging": True,
        },
        "memory": {
            "enabled": True,
            "project_memory_enabled": True,
            "auto_capture_decisions": True,
            "auto_capture_tool_lessons": True,
            "max_context_memories": 8,
            "default_ttl_days": None,
            "redaction_enabled": True,
            "require_provenance": True,
            "compaction_enabled": True,
        },
        "code": {
            "enabled": True,
            "auto_scan": True,
            "test_timeout_seconds": 120,
            "max_output_chars": 12000,
            "allow_npm_install": True,
            "allow_pip_install": True,
            "allow_git_commit": True,
            "allow_git_push": False,
        },
        "self_healing": {
            "enabled": True,
            "max_attempts": 1,
            "auto_apply_safe_recoveries": False,
        },
        "evals": {
            "enabled": True,
            "auto_score_runs": True,
            "collect_metrics": True,
            "redact_traces": True,
            "max_trace_chars": 20000,
            "failure_clustering_enabled": True,
            "default_dataset_dir": "~/.omega/evals",
            "report_dir": "~/.omega/eval_reports",
        },
        "workflows": {
            "enabled": True,
            "max_steps": 30,
            "max_duration_seconds": 900,
            "allow_nested_workflows": False,
            "templates_enabled": True,
            "require_approval_for_destructive_steps": True,
        },
        "connectors": {
            "enabled": True,
            "openapi_import_enabled": True,
            "untrusted_disabled_by_default": True,
            "max_response_chars": 20000,
            "timeout_seconds": 30,
            "github": {"enabled": False},
            "local_http": {"enabled": False},
            "browser_fallback_enabled": False,
        },
        "events": {
            "enabled": True,
            "persist": True,
            "replay_enabled": True,
            "max_replay_events": 500,
            "redaction_enabled": True,
            "websocket_heartbeat_seconds": 20,
        },
        "research": {
            "enabled": True,
            "max_sources": 20,
            "max_claims": 50,
            "require_evidence_for_claims": True,
            "export_dir": "research_reports",
            "web_enabled": False,
            "external_sources_untrusted": True,
        },
        "skills": {
            "enabled": True,
            "foundry_enabled": True,
            "auto_detect_candidates": False,
            "min_successful_runs_for_candidate": 2,
            "require_user_approval_for_promotion": True,
            "max_skills_in_context": 5,
            "test_before_activation": True,
        },
        "governance": {
            "budgets": {
                "enabled": True,
                "default_profile": "Default Local",
                "enforce": True,
                "warning_threshold": 0.8,
            },
            "risk_governor": {
                "enabled": True,
                "default_max_risk": "high",
            },
        },
        "shadow": {
            "enabled": True,
            "require_for_high_risk": True,
            "require_for_workflows_over_steps": 5,
            "workspace_keep_days": 3,
            "max_shadow_seconds": 300,
            "allow_shell_in_shadow": True,
            "auto_promote_low_risk": False,
            "compare_after_live": True,
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
    "OMEGA_MOBILE_MODE": "mobile.mode",
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
    "OMEGA_RUNTIME_CHECKPOINTS_ENABLED": "runtime.checkpoints.enabled",
    "OMEGA_RUNTIME_SNAPSHOTS_ENABLED": "runtime.snapshots.enabled",
    "OMEGA_RUNTIME_SNAPSHOTS_MAX_FILE_SIZE_MB": "runtime.snapshots.max_file_size_mb",
    "OMEGA_RUNTIME_SNAPSHOTS_KEEP_DAYS": "runtime.snapshots.keep_days",
    "OMEGA_RUNTIME_REPLAY_ENABLED": "runtime.replay.enabled",
    "OMEGA_RUNTIME_RESUME_INTERRUPTED_RUNS": "runtime.resume_interrupted_runs",
    "OMEGA_RUNTIME_MAX_TOOL_ITERATIONS": "runtime.max_tool_iterations",
    "OMEGA_RUNTIME_MAX_ACTIONS_PER_TURN": "runtime.max_actions_per_turn",
    "OMEGA_RUNTIME_MAX_RUN_SECONDS": "runtime.max_run_seconds",
    "OMEGA_RUNTIME_DEAD_LETTER_ENABLED": "runtime.dead_letter_enabled",
    "OMEGA_CAPABILITIES_ENABLED": "capabilities.enabled",
    "OMEGA_CAPABILITIES_MAX_IN_CONTEXT": "capabilities.max_in_context",
    "OMEGA_CAPABILITIES_MCP_ENABLED": "capabilities.mcp_enabled",
    "OMEGA_CAPABILITIES_A2A_ENABLED": "capabilities.a2a_enabled",
    "OMEGA_CAPABILITIES_UNTRUSTED_DISABLED_BY_DEFAULT": "capabilities.untrusted_disabled_by_default",
    "OMEGA_CAPABILITIES_USAGE_LOGGING": "capabilities.usage_logging",
    "OMEGA_MEMORY_ENABLED": "memory.enabled",
    "OMEGA_MEMORY_PROJECT_MEMORY_ENABLED": "memory.project_memory_enabled",
    "OMEGA_MEMORY_AUTO_CAPTURE_DECISIONS": "memory.auto_capture_decisions",
    "OMEGA_MEMORY_AUTO_CAPTURE_TOOL_LESSONS": "memory.auto_capture_tool_lessons",
    "OMEGA_MEMORY_MAX_CONTEXT_MEMORIES": "memory.max_context_memories",
    "OMEGA_MEMORY_DEFAULT_TTL_DAYS": "memory.default_ttl_days",
    "OMEGA_MEMORY_REDACTION_ENABLED": "memory.redaction_enabled",
    "OMEGA_MEMORY_REQUIRE_PROVENANCE": "memory.require_provenance",
    "OMEGA_MEMORY_COMPACTION_ENABLED": "memory.compaction_enabled",
    "OMEGA_CODE_ENABLED": "code.enabled",
    "OMEGA_CODE_AUTO_SCAN": "code.auto_scan",
    "OMEGA_CODE_TEST_TIMEOUT_SECONDS": "code.test_timeout_seconds",
    "OMEGA_CODE_MAX_OUTPUT_CHARS": "code.max_output_chars",
    "OMEGA_CODE_ALLOW_NPM_INSTALL": "code.allow_npm_install",
    "OMEGA_CODE_ALLOW_PIP_INSTALL": "code.allow_pip_install",
    "OMEGA_CODE_ALLOW_GIT_COMMIT": "code.allow_git_commit",
    "OMEGA_CODE_ALLOW_GIT_PUSH": "code.allow_git_push",
    "OMEGA_SELF_HEALING_ENABLED": "self_healing.enabled",
    "OMEGA_SELF_HEALING_MAX_ATTEMPTS": "self_healing.max_attempts",
    "OMEGA_SELF_HEALING_AUTO_APPLY_SAFE_RECOVERIES": "self_healing.auto_apply_safe_recoveries",
    "OMEGA_EVALS_ENABLED": "evals.enabled",
    "OMEGA_EVALS_AUTO_SCORE_RUNS": "evals.auto_score_runs",
    "OMEGA_EVALS_COLLECT_METRICS": "evals.collect_metrics",
    "OMEGA_EVALS_REDACT_TRACES": "evals.redact_traces",
    "OMEGA_EVALS_MAX_TRACE_CHARS": "evals.max_trace_chars",
    "OMEGA_EVALS_FAILURE_CLUSTERING_ENABLED": "evals.failure_clustering_enabled",
    "OMEGA_EVALS_DEFAULT_DATASET_DIR": "evals.default_dataset_dir",
    "OMEGA_EVALS_REPORT_DIR": "evals.report_dir",
    "OMEGA_WORKFLOWS_ENABLED": "workflows.enabled",
    "OMEGA_WORKFLOWS_MAX_STEPS": "workflows.max_steps",
    "OMEGA_WORKFLOWS_MAX_DURATION_SECONDS": "workflows.max_duration_seconds",
    "OMEGA_WORKFLOWS_ALLOW_NESTED_WORKFLOWS": "workflows.allow_nested_workflows",
    "OMEGA_WORKFLOWS_TEMPLATES_ENABLED": "workflows.templates_enabled",
    "OMEGA_WORKFLOWS_REQUIRE_APPROVAL_FOR_DESTRUCTIVE_STEPS": "workflows.require_approval_for_destructive_steps",
    "OMEGA_CONNECTORS_ENABLED": "connectors.enabled",
    "OMEGA_CONNECTORS_OPENAPI_IMPORT_ENABLED": "connectors.openapi_import_enabled",
    "OMEGA_CONNECTORS_UNTRUSTED_DISABLED_BY_DEFAULT": "connectors.untrusted_disabled_by_default",
    "OMEGA_CONNECTORS_MAX_RESPONSE_CHARS": "connectors.max_response_chars",
    "OMEGA_CONNECTORS_TIMEOUT_SECONDS": "connectors.timeout_seconds",
    "OMEGA_CONNECTORS_GITHUB_ENABLED": "connectors.github.enabled",
    "OMEGA_CONNECTORS_LOCAL_HTTP_ENABLED": "connectors.local_http.enabled",
    "OMEGA_CONNECTORS_BROWSER_FALLBACK_ENABLED": "connectors.browser_fallback_enabled",
    "OMEGA_EVENTS_ENABLED": "events.enabled",
    "OMEGA_EVENTS_PERSIST": "events.persist",
    "OMEGA_EVENTS_REPLAY_ENABLED": "events.replay_enabled",
    "OMEGA_EVENTS_MAX_REPLAY_EVENTS": "events.max_replay_events",
    "OMEGA_EVENTS_REDACTION_ENABLED": "events.redaction_enabled",
    "OMEGA_EVENTS_WEBSOCKET_HEARTBEAT_SECONDS": "events.websocket_heartbeat_seconds",
    "OMEGA_RESEARCH_ENABLED": "research.enabled",
    "OMEGA_RESEARCH_MAX_SOURCES": "research.max_sources",
    "OMEGA_RESEARCH_MAX_CLAIMS": "research.max_claims",
    "OMEGA_RESEARCH_REQUIRE_EVIDENCE_FOR_CLAIMS": "research.require_evidence_for_claims",
    "OMEGA_RESEARCH_EXPORT_DIR": "research.export_dir",
    "OMEGA_RESEARCH_WEB_ENABLED": "research.web_enabled",
    "OMEGA_RESEARCH_EXTERNAL_SOURCES_UNTRUSTED": "research.external_sources_untrusted",
    "OMEGA_SKILLS_ENABLED": "skills.enabled",
    "OMEGA_SKILLS_FOUNDRY_ENABLED": "skills.foundry_enabled",
    "OMEGA_SKILLS_AUTO_DETECT_CANDIDATES": "skills.auto_detect_candidates",
    "OMEGA_SKILLS_MIN_SUCCESSFUL_RUNS_FOR_CANDIDATE": "skills.min_successful_runs_for_candidate",
    "OMEGA_SKILLS_REQUIRE_USER_APPROVAL_FOR_PROMOTION": "skills.require_user_approval_for_promotion",
    "OMEGA_SKILLS_MAX_SKILLS_IN_CONTEXT": "skills.max_skills_in_context",
    "OMEGA_SKILLS_TEST_BEFORE_ACTIVATION": "skills.test_before_activation",
    "OMEGA_GOVERNANCE_BUDGETS_ENABLED": "governance.budgets.enabled",
    "OMEGA_GOVERNANCE_BUDGETS_DEFAULT_PROFILE": "governance.budgets.default_profile",
    "OMEGA_GOVERNANCE_BUDGETS_ENFORCE": "governance.budgets.enforce",
    "OMEGA_GOVERNANCE_BUDGETS_WARNING_THRESHOLD": "governance.budgets.warning_threshold",
    "OMEGA_GOVERNANCE_RISK_GOVERNOR_ENABLED": "governance.risk_governor.enabled",
    "OMEGA_GOVERNANCE_RISK_GOVERNOR_DEFAULT_MAX_RISK": "governance.risk_governor.default_max_risk",
    "OMEGA_SHADOW_ENABLED": "shadow.enabled",
    "OMEGA_SHADOW_REQUIRE_FOR_HIGH_RISK": "shadow.require_for_high_risk",
    "OMEGA_SHADOW_REQUIRE_FOR_WORKFLOWS_OVER_STEPS": "shadow.require_for_workflows_over_steps",
    "OMEGA_SHADOW_WORKSPACE_KEEP_DAYS": "shadow.workspace_keep_days",
    "OMEGA_SHADOW_MAX_SHADOW_SECONDS": "shadow.max_shadow_seconds",
    "OMEGA_SHADOW_ALLOW_SHELL_IN_SHADOW": "shadow.allow_shell_in_shadow",
    "OMEGA_SHADOW_AUTO_PROMOTE_LOW_RISK": "shadow.auto_promote_low_risk",
    "OMEGA_SHADOW_COMPARE_AFTER_LIVE": "shadow.compare_after_live",
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
            loaded = json.loads(target.read_text(encoding="utf-8-sig"))
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
