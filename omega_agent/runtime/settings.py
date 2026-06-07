from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import is_sensitive_key, redact

PUBLIC_SETTINGS = {
    "provider",
    "model",
    "workspace",
    "host",
    "port",
    "open_browser",
    "safe_mode",
    "require_approvals",
    "workspace_full_access",
    "require_approval_outside_workspace",
    "shell_full_access_in_workspace",
    "allow_delete_in_workspace",
    "allow_git_write_in_workspace",
    "skills_dir",
    "plugins_dir",
    "theme",
    "channels_enabled",
    "webhooks_enabled",
    "telegram_enabled",
    "discord_enabled",
    "scheduler_enabled",
    "scheduler_tick_seconds",
    "reasoning_stream",
    "reasoning_detail",
    "default_model_ref",
    "fallback_model_ref",
    "model_selection_enabled",
    "config_path",
    "config_status",
    "legacy_env_present",
    "model_config_source",
}
PATCHABLE_SETTINGS = {
    "provider",
    "model",
    "open_browser",
    "safe_mode",
    "require_approvals",
    "workspace_full_access",
    "require_approval_outside_workspace",
    "shell_full_access_in_workspace",
    "allow_delete_in_workspace",
    "allow_git_write_in_workspace",
    "theme",
    "default_model_ref",
    "fallback_model_ref",
    "model_selection_enabled",
}


@dataclass(frozen=True)
class SettingsStore:
    config: OmegaConfig

    def get_all(self) -> dict:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
        stored = {
            row["key"]: redact(json.loads(row["value_json"]))
            for row in rows
            if row["key"] in PUBLIC_SETTINGS and not is_sensitive_key(row["key"])
        }
        defaults = {
            "provider": self.config.provider,
            "model": self.config.model,
            "workspace": str(self.config.workspace),
            "host": self.config.host,
            "port": self.config.port,
            "open_browser": self.config.open_browser,
            "safe_mode": self.config.safe_mode,
            "require_approvals": self.config.require_approval,
            "workspace_full_access": self.config.workspace_full_access,
            "require_approval_outside_workspace": self.config.require_approval_outside_workspace,
            "shell_full_access_in_workspace": self.config.shell_full_access_in_workspace,
            "allow_delete_in_workspace": self.config.allow_delete_in_workspace,
            "allow_git_write_in_workspace": self.config.allow_git_write_in_workspace,
            "skills_dir": str(self.config.skills_dir),
            "plugins_dir": str(self.config.plugins_dir),
            "theme": self.config.ui_theme,
            "channels_enabled": self.config.channels_enabled,
            "webhooks_enabled": self.config.webhooks_enabled,
            "telegram_enabled": self.config.telegram_enabled,
            "discord_enabled": self.config.discord_enabled,
            "scheduler_enabled": self.config.scheduler_enabled,
            "scheduler_tick_seconds": self.config.scheduler_tick_seconds,
            "reasoning_stream": self.config.reasoning_stream,
            "reasoning_detail": self.config.reasoning_detail,
            "default_model_ref": self.config.default_model_ref,
            "fallback_model_ref": self.config.fallback_model_ref,
            "model_selection_enabled": self.config.model_selection_enabled,
            "config_path": str(self.config.config_path),
            "config_status": self.config.config_status,
            "legacy_env_present": self.config.legacy_env_present,
            "model_config_source": self.config.model_config_source,
        }
        defaults.update(stored)
        return redact(defaults)

    def patch(self, values: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            for key, value in values.items():
                if is_sensitive_key(key):
                    raise ValueError(f"Setting sensible refuse: {key}")
                if key not in PATCHABLE_SETTINGS:
                    raise ValueError(f"Setting non modifiable: {key}")
                conn.execute(
                    "INSERT OR REPLACE INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
        return self.get_all()
