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
    mobile_mode: str = "tailscale"
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
    runtime_checkpoints_enabled: bool = True
    runtime_snapshots_enabled: bool = True
    runtime_snapshots_max_file_size_mb: int = 10
    runtime_snapshots_keep_days: int = 30
    runtime_replay_enabled: bool = True
    runtime_resume_interrupted_runs: bool = False
    runtime_max_tool_iterations: int = 5
    runtime_max_actions_per_turn: int = 10
    runtime_max_run_seconds: int = 300
    runtime_dead_letter_enabled: bool = True
    capabilities_enabled: bool = True
    capabilities_max_in_context: int = 20
    capabilities_mcp_enabled: bool = False
    capabilities_a2a_enabled: bool = False
    capabilities_untrusted_disabled_by_default: bool = True
    capabilities_usage_logging: bool = True
    memory_enabled: bool = True
    memory_project_memory_enabled: bool = True
    memory_auto_capture_decisions: bool = True
    memory_auto_capture_tool_lessons: bool = True
    memory_max_context_memories: int = 8
    memory_default_ttl_days: int | None = None
    memory_redaction_enabled: bool = True
    memory_require_provenance: bool = True
    memory_compaction_enabled: bool = True
    code_enabled: bool = True
    code_auto_scan: bool = True
    code_test_timeout_seconds: int = 120
    code_max_output_chars: int = 12000
    code_allow_npm_install: bool = True
    code_allow_pip_install: bool = True
    code_allow_git_commit: bool = True
    code_allow_git_push: bool = False
    self_healing_enabled: bool = True
    self_healing_max_attempts: int = 1
    self_healing_auto_apply_safe_recoveries: bool = False
    evals_enabled: bool = True
    evals_auto_score_runs: bool = True
    evals_collect_metrics: bool = True
    evals_redact_traces: bool = True
    evals_max_trace_chars: int = 20000
    evals_failure_clustering_enabled: bool = True
    evals_default_dataset_dir: Path | None = None
    evals_report_dir: Path | None = None
    workflows_enabled: bool = True
    workflows_max_steps: int = 30
    workflows_max_duration_seconds: int = 900
    workflows_allow_nested_workflows: bool = False
    workflows_templates_enabled: bool = True
    workflows_require_approval_for_destructive_steps: bool = True
    connectors_enabled: bool = True
    connectors_openapi_import_enabled: bool = True
    connectors_untrusted_disabled_by_default: bool = True
    connectors_max_response_chars: int = 20000
    connectors_timeout_seconds: int = 30
    connectors_github_enabled: bool = False
    connectors_local_http_enabled: bool = False
    connectors_browser_fallback_enabled: bool = False
    events_enabled: bool = True
    events_persist: bool = True
    events_replay_enabled: bool = True
    events_max_replay_events: int = 500
    events_redaction_enabled: bool = True
    events_websocket_heartbeat_seconds: int = 20
    research_enabled: bool = True
    research_max_sources: int = 20
    research_max_claims: int = 50
    research_require_evidence_for_claims: bool = True
    research_export_dir: str = "research_reports"
    research_web_enabled: bool = False
    research_external_sources_untrusted: bool = True
    skills_enabled: bool = True
    skills_foundry_enabled: bool = True
    skills_auto_detect_candidates: bool = False
    skills_min_successful_runs_for_candidate: int = 2
    skills_require_user_approval_for_promotion: bool = True
    skills_max_skills_in_context: int = 5
    skills_test_before_activation: bool = True
    governance_budgets_enabled: bool = True
    governance_budgets_default_profile: str = "Default Local"
    governance_budgets_enforce: bool = True
    governance_budgets_warning_threshold: float = 0.8
    governance_risk_governor_enabled: bool = True
    governance_risk_governor_default_max_risk: str = "high"
    shadow_enabled: bool = True
    shadow_require_for_high_risk: bool = True
    shadow_require_for_workflows_over_steps: int = 5
    shadow_workspace_keep_days: int = 3
    shadow_max_shadow_seconds: int = 300
    shadow_allow_shell_in_shadow: bool = True
    shadow_auto_promote_low_risk: bool = False
    shadow_compare_after_live: bool = True
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
        if self.evals_default_dataset_dir:
            self.evals_default_dataset_dir.mkdir(parents=True, exist_ok=True)
        if self.evals_report_dir:
            self.evals_report_dir.mkdir(parents=True, exist_ok=True)

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
            mobile_mode=_parse_mobile_mode(source.get("OMEGA_MOBILE_MODE", "tailscale", "mobile.mode")),
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
            runtime_checkpoints_enabled=_parse_bool(source.get("OMEGA_RUNTIME_CHECKPOINTS_ENABLED", "true", "runtime.checkpoints.enabled")),
            runtime_snapshots_enabled=_parse_bool(source.get("OMEGA_RUNTIME_SNAPSHOTS_ENABLED", "true", "runtime.snapshots.enabled")),
            runtime_snapshots_max_file_size_mb=max(1, _parse_int(source.get("OMEGA_RUNTIME_SNAPSHOTS_MAX_FILE_SIZE_MB", "10", "runtime.snapshots.max_file_size_mb"), 10)),
            runtime_snapshots_keep_days=max(1, _parse_int(source.get("OMEGA_RUNTIME_SNAPSHOTS_KEEP_DAYS", "30", "runtime.snapshots.keep_days"), 30)),
            runtime_replay_enabled=_parse_bool(source.get("OMEGA_RUNTIME_REPLAY_ENABLED", "true", "runtime.replay.enabled")),
            runtime_resume_interrupted_runs=_parse_bool(source.get("OMEGA_RUNTIME_RESUME_INTERRUPTED_RUNS", "false", "runtime.resume_interrupted_runs")),
            runtime_max_tool_iterations=max(1, _parse_int(source.get("OMEGA_RUNTIME_MAX_TOOL_ITERATIONS", "5", "runtime.max_tool_iterations"), 5)),
            runtime_max_actions_per_turn=max(1, _parse_int(source.get("OMEGA_RUNTIME_MAX_ACTIONS_PER_TURN", "10", "runtime.max_actions_per_turn"), 10)),
            runtime_max_run_seconds=max(1, _parse_int(source.get("OMEGA_RUNTIME_MAX_RUN_SECONDS", "300", "runtime.max_run_seconds"), 300)),
            runtime_dead_letter_enabled=_parse_bool(source.get("OMEGA_RUNTIME_DEAD_LETTER_ENABLED", "true", "runtime.dead_letter_enabled")),
            capabilities_enabled=_parse_bool(source.get("OMEGA_CAPABILITIES_ENABLED", "true", "capabilities.enabled")),
            capabilities_max_in_context=max(1, _parse_int(source.get("OMEGA_CAPABILITIES_MAX_IN_CONTEXT", "20", "capabilities.max_in_context"), 20)),
            capabilities_mcp_enabled=_parse_bool(source.get("OMEGA_CAPABILITIES_MCP_ENABLED", "false", "capabilities.mcp_enabled")),
            capabilities_a2a_enabled=_parse_bool(source.get("OMEGA_CAPABILITIES_A2A_ENABLED", "false", "capabilities.a2a_enabled")),
            capabilities_untrusted_disabled_by_default=_parse_bool(source.get("OMEGA_CAPABILITIES_UNTRUSTED_DISABLED_BY_DEFAULT", "true", "capabilities.untrusted_disabled_by_default")),
            capabilities_usage_logging=_parse_bool(source.get("OMEGA_CAPABILITIES_USAGE_LOGGING", "true", "capabilities.usage_logging")),
            memory_enabled=_parse_bool(source.get("OMEGA_MEMORY_ENABLED", "true", "memory.enabled")),
            memory_project_memory_enabled=_parse_bool(source.get("OMEGA_MEMORY_PROJECT_MEMORY_ENABLED", "true", "memory.project_memory_enabled")),
            memory_auto_capture_decisions=_parse_bool(source.get("OMEGA_MEMORY_AUTO_CAPTURE_DECISIONS", "true", "memory.auto_capture_decisions")),
            memory_auto_capture_tool_lessons=_parse_bool(source.get("OMEGA_MEMORY_AUTO_CAPTURE_TOOL_LESSONS", "true", "memory.auto_capture_tool_lessons")),
            memory_max_context_memories=max(1, _parse_int(source.get("OMEGA_MEMORY_MAX_CONTEXT_MEMORIES", "8", "memory.max_context_memories"), 8)),
            memory_default_ttl_days=_parse_optional_positive_int(source.get("OMEGA_MEMORY_DEFAULT_TTL_DAYS", "", "memory.default_ttl_days")),
            memory_redaction_enabled=_parse_bool(source.get("OMEGA_MEMORY_REDACTION_ENABLED", "true", "memory.redaction_enabled")),
            memory_require_provenance=_parse_bool(source.get("OMEGA_MEMORY_REQUIRE_PROVENANCE", "true", "memory.require_provenance")),
            memory_compaction_enabled=_parse_bool(source.get("OMEGA_MEMORY_COMPACTION_ENABLED", "true", "memory.compaction_enabled")),
            code_enabled=_parse_bool(source.get("OMEGA_CODE_ENABLED", "true", "code.enabled")),
            code_auto_scan=_parse_bool(source.get("OMEGA_CODE_AUTO_SCAN", "true", "code.auto_scan")),
            code_test_timeout_seconds=max(1, _parse_int(source.get("OMEGA_CODE_TEST_TIMEOUT_SECONDS", "120", "code.test_timeout_seconds"), 120)),
            code_max_output_chars=max(1000, _parse_int(source.get("OMEGA_CODE_MAX_OUTPUT_CHARS", "12000", "code.max_output_chars"), 12000)),
            code_allow_npm_install=_parse_bool(source.get("OMEGA_CODE_ALLOW_NPM_INSTALL", "true", "code.allow_npm_install")),
            code_allow_pip_install=_parse_bool(source.get("OMEGA_CODE_ALLOW_PIP_INSTALL", "true", "code.allow_pip_install")),
            code_allow_git_commit=_parse_bool(source.get("OMEGA_CODE_ALLOW_GIT_COMMIT", "true", "code.allow_git_commit")),
            code_allow_git_push=_parse_bool(source.get("OMEGA_CODE_ALLOW_GIT_PUSH", "false", "code.allow_git_push")),
            self_healing_enabled=_parse_bool(source.get("OMEGA_SELF_HEALING_ENABLED", "true", "self_healing.enabled")),
            self_healing_max_attempts=max(0, _parse_int(source.get("OMEGA_SELF_HEALING_MAX_ATTEMPTS", "1", "self_healing.max_attempts"), 1)),
            self_healing_auto_apply_safe_recoveries=_parse_bool(source.get("OMEGA_SELF_HEALING_AUTO_APPLY_SAFE_RECOVERIES", "false", "self_healing.auto_apply_safe_recoveries")),
            evals_enabled=_parse_bool(source.get("OMEGA_EVALS_ENABLED", "true", "evals.enabled")),
            evals_auto_score_runs=_parse_bool(source.get("OMEGA_EVALS_AUTO_SCORE_RUNS", "true", "evals.auto_score_runs")),
            evals_collect_metrics=_parse_bool(source.get("OMEGA_EVALS_COLLECT_METRICS", "true", "evals.collect_metrics")),
            evals_redact_traces=_parse_bool(source.get("OMEGA_EVALS_REDACT_TRACES", "true", "evals.redact_traces")),
            evals_max_trace_chars=max(1000, _parse_int(source.get("OMEGA_EVALS_MAX_TRACE_CHARS", "20000", "evals.max_trace_chars"), 20000)),
            evals_failure_clustering_enabled=_parse_bool(source.get("OMEGA_EVALS_FAILURE_CLUSTERING_ENABLED", "true", "evals.failure_clustering_enabled")),
            evals_default_dataset_dir=Path(source.get("OMEGA_EVALS_DEFAULT_DATASET_DIR", "~/.omega/evals", "evals.default_dataset_dir").strip()).expanduser().resolve(),
            evals_report_dir=Path(source.get("OMEGA_EVALS_REPORT_DIR", "~/.omega/eval_reports", "evals.report_dir").strip()).expanduser().resolve(),
            workflows_enabled=_parse_bool(source.get("OMEGA_WORKFLOWS_ENABLED", "true", "workflows.enabled")),
            workflows_max_steps=max(1, _parse_int(source.get("OMEGA_WORKFLOWS_MAX_STEPS", "30", "workflows.max_steps"), 30)),
            workflows_max_duration_seconds=max(1, _parse_int(source.get("OMEGA_WORKFLOWS_MAX_DURATION_SECONDS", "900", "workflows.max_duration_seconds"), 900)),
            workflows_allow_nested_workflows=_parse_bool(source.get("OMEGA_WORKFLOWS_ALLOW_NESTED_WORKFLOWS", "false", "workflows.allow_nested_workflows")),
            workflows_templates_enabled=_parse_bool(source.get("OMEGA_WORKFLOWS_TEMPLATES_ENABLED", "true", "workflows.templates_enabled")),
            workflows_require_approval_for_destructive_steps=_parse_bool(source.get("OMEGA_WORKFLOWS_REQUIRE_APPROVAL_FOR_DESTRUCTIVE_STEPS", "true", "workflows.require_approval_for_destructive_steps")),
            connectors_enabled=_parse_bool(source.get("OMEGA_CONNECTORS_ENABLED", "true", "connectors.enabled")),
            connectors_openapi_import_enabled=_parse_bool(source.get("OMEGA_CONNECTORS_OPENAPI_IMPORT_ENABLED", "true", "connectors.openapi_import_enabled")),
            connectors_untrusted_disabled_by_default=_parse_bool(source.get("OMEGA_CONNECTORS_UNTRUSTED_DISABLED_BY_DEFAULT", "true", "connectors.untrusted_disabled_by_default")),
            connectors_max_response_chars=max(1000, _parse_int(source.get("OMEGA_CONNECTORS_MAX_RESPONSE_CHARS", "20000", "connectors.max_response_chars"), 20000)),
            connectors_timeout_seconds=max(1, _parse_int(source.get("OMEGA_CONNECTORS_TIMEOUT_SECONDS", "30", "connectors.timeout_seconds"), 30)),
            connectors_github_enabled=_parse_bool(source.get("OMEGA_CONNECTORS_GITHUB_ENABLED", "false", "connectors.github.enabled")),
            connectors_local_http_enabled=_parse_bool(source.get("OMEGA_CONNECTORS_LOCAL_HTTP_ENABLED", "false", "connectors.local_http.enabled")),
            connectors_browser_fallback_enabled=_parse_bool(source.get("OMEGA_CONNECTORS_BROWSER_FALLBACK_ENABLED", "false", "connectors.browser_fallback_enabled")),
            events_enabled=_parse_bool(source.get("OMEGA_EVENTS_ENABLED", "true", "events.enabled")),
            events_persist=_parse_bool(source.get("OMEGA_EVENTS_PERSIST", "true", "events.persist")),
            events_replay_enabled=_parse_bool(source.get("OMEGA_EVENTS_REPLAY_ENABLED", "true", "events.replay_enabled")),
            events_max_replay_events=max(1, _parse_int(source.get("OMEGA_EVENTS_MAX_REPLAY_EVENTS", "500", "events.max_replay_events"), 500)),
            events_redaction_enabled=_parse_bool(source.get("OMEGA_EVENTS_REDACTION_ENABLED", "true", "events.redaction_enabled")),
            events_websocket_heartbeat_seconds=max(5, _parse_int(source.get("OMEGA_EVENTS_WEBSOCKET_HEARTBEAT_SECONDS", "20", "events.websocket_heartbeat_seconds"), 20)),
            research_enabled=_parse_bool(source.get("OMEGA_RESEARCH_ENABLED", "true", "research.enabled")),
            research_max_sources=max(1, _parse_int(source.get("OMEGA_RESEARCH_MAX_SOURCES", "20", "research.max_sources"), 20)),
            research_max_claims=max(1, _parse_int(source.get("OMEGA_RESEARCH_MAX_CLAIMS", "50", "research.max_claims"), 50)),
            research_require_evidence_for_claims=_parse_bool(source.get("OMEGA_RESEARCH_REQUIRE_EVIDENCE_FOR_CLAIMS", "true", "research.require_evidence_for_claims")),
            research_export_dir=source.get("OMEGA_RESEARCH_EXPORT_DIR", "research_reports", "research.export_dir").strip() or "research_reports",
            research_web_enabled=_parse_bool(source.get("OMEGA_RESEARCH_WEB_ENABLED", "false", "research.web_enabled")),
            research_external_sources_untrusted=_parse_bool(source.get("OMEGA_RESEARCH_EXTERNAL_SOURCES_UNTRUSTED", "true", "research.external_sources_untrusted")),
            skills_enabled=_parse_bool(source.get("OMEGA_SKILLS_ENABLED", "true", "skills.enabled")),
            skills_foundry_enabled=_parse_bool(source.get("OMEGA_SKILLS_FOUNDRY_ENABLED", "true", "skills.foundry_enabled")),
            skills_auto_detect_candidates=_parse_bool(source.get("OMEGA_SKILLS_AUTO_DETECT_CANDIDATES", "false", "skills.auto_detect_candidates")),
            skills_min_successful_runs_for_candidate=max(2, _parse_int(source.get("OMEGA_SKILLS_MIN_SUCCESSFUL_RUNS_FOR_CANDIDATE", "2", "skills.min_successful_runs_for_candidate"), 2)),
            skills_require_user_approval_for_promotion=_parse_bool(source.get("OMEGA_SKILLS_REQUIRE_USER_APPROVAL_FOR_PROMOTION", "true", "skills.require_user_approval_for_promotion")),
            skills_max_skills_in_context=max(1, _parse_int(source.get("OMEGA_SKILLS_MAX_SKILLS_IN_CONTEXT", "5", "skills.max_skills_in_context"), 5)),
            skills_test_before_activation=_parse_bool(source.get("OMEGA_SKILLS_TEST_BEFORE_ACTIVATION", "true", "skills.test_before_activation")),
            governance_budgets_enabled=_parse_bool(source.get("OMEGA_GOVERNANCE_BUDGETS_ENABLED", "true", "governance.budgets.enabled")),
            governance_budgets_default_profile=source.get("OMEGA_GOVERNANCE_BUDGETS_DEFAULT_PROFILE", "Default Local", "governance.budgets.default_profile").strip() or "Default Local",
            governance_budgets_enforce=_parse_bool(source.get("OMEGA_GOVERNANCE_BUDGETS_ENFORCE", "true", "governance.budgets.enforce")),
            governance_budgets_warning_threshold=max(0.1, min(1.0, _parse_float(source.get("OMEGA_GOVERNANCE_BUDGETS_WARNING_THRESHOLD", "0.8", "governance.budgets.warning_threshold"), 0.8))),
            governance_risk_governor_enabled=_parse_bool(source.get("OMEGA_GOVERNANCE_RISK_GOVERNOR_ENABLED", "true", "governance.risk_governor.enabled")),
            governance_risk_governor_default_max_risk=source.get("OMEGA_GOVERNANCE_RISK_GOVERNOR_DEFAULT_MAX_RISK", "high", "governance.risk_governor.default_max_risk").strip().lower() or "high",
            shadow_enabled=_parse_bool(source.get("OMEGA_SHADOW_ENABLED", "true", "shadow.enabled")),
            shadow_require_for_high_risk=_parse_bool(source.get("OMEGA_SHADOW_REQUIRE_FOR_HIGH_RISK", "true", "shadow.require_for_high_risk")),
            shadow_require_for_workflows_over_steps=max(1, _parse_nonnegative_int(source.get("OMEGA_SHADOW_REQUIRE_FOR_WORKFLOWS_OVER_STEPS", "5", "shadow.require_for_workflows_over_steps"), 5)),
            shadow_workspace_keep_days=max(0, _parse_nonnegative_int(source.get("OMEGA_SHADOW_WORKSPACE_KEEP_DAYS", "3", "shadow.workspace_keep_days"), 3)),
            shadow_max_shadow_seconds=max(1, _parse_nonnegative_int(source.get("OMEGA_SHADOW_MAX_SHADOW_SECONDS", "300", "shadow.max_shadow_seconds"), 300)),
            shadow_allow_shell_in_shadow=_parse_bool(source.get("OMEGA_SHADOW_ALLOW_SHELL_IN_SHADOW", "true", "shadow.allow_shell_in_shadow")),
            shadow_auto_promote_low_risk=_parse_bool(source.get("OMEGA_SHADOW_AUTO_PROMOTE_LOW_RISK", "false", "shadow.auto_promote_low_risk")),
            shadow_compare_after_live=_parse_bool(source.get("OMEGA_SHADOW_COMPARE_AFTER_LIVE", "true", "shadow.compare_after_live")),
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
        self.config_exists = self.config_file.exists() and not _ignore_user_config_for_tests()
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


def _ignore_user_config_for_tests() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST")) and not os.getenv("OMEGA_CONFIG_PATH")


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


def _parse_mobile_mode(value: str) -> str:
    mode = value.strip().lower() or "tailscale"
    if mode not in {"tailscale", "off"}:
        raise ValueError("mobile.mode doit valoir tailscale ou off.")
    return mode


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


def _parse_float(value: str, default: float) -> float:
    try:
        return float(value.strip() or str(default))
    except ValueError as exc:
        raise ValueError("Valeur numerique invalide.") from exc


def _parse_nonnegative_int(value: str, default: int) -> int:
    return max(0, _parse_int(value, default))


def _parse_optional_positive_int(value: str) -> int | None:
    stripped = value.strip()
    if stripped.lower() in {"", "none", "null"}:
        return None
    return max(1, _parse_int(stripped, 1))
