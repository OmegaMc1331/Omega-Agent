from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact
from omega_agent.security.risk import score_risk
from omega_agent.security.sandbox import safe_path

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
POLICY_EFFECTS = {"allow", "deny", "require_approval"}
ACTION_CATEGORIES = {"read_only", "reversible_write", "destructive_write", "external_side_effect", "system_sensitive"}

READ_ONLY_TOOLS = {"list_files", "list_tree", "read_file", "file_exists", "git_status", "git_diff", "git_log", "git_branch", "git_show"}
REVERSIBLE_WRITE_TOOLS = {"write_file", "append_file", "create_directory", "copy_file", "git_add", "git_commit", "git_restore_file"}
DESTRUCTIVE_WRITE_TOOLS = {"delete_file", "delete_directory", "move_file"}
EXTERNAL_SIDE_EFFECT_TOOLS = {"git_push", "browser_open_url", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}
SYSTEM_SENSITIVE_TOOLS = {"sudo", "runas", "set_execution_policy", "system_exec"}


@dataclass(frozen=True)
class PolicyRule:
    id: str
    profile_id: str
    name: str
    description: str
    enabled: bool
    priority: int
    effect: str
    action_type: str | None
    tool_name: str | None
    resource_pattern: str | None
    risk_level_min: str | None
    conditions: dict[str, Any]
    reason: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(
            {
                "id": self.id,
                "profile_id": self.profile_id,
                "name": self.name,
                "description": self.description,
                "enabled": self.enabled,
                "priority": self.priority,
                "effect": self.effect,
                "action_type": self.action_type,
                "tool_name": self.tool_name,
                "resource_pattern": self.resource_pattern,
                "risk_level_min": self.risk_level_min,
                "conditions": self.conditions,
                "reason": self.reason,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "metadata": self.metadata,
            }
        )


def classify_action(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    args = arguments or {}
    command = str(args.get("command") or "").lower()
    if tool_name == "invoke_connector_operation":
        category = str(args.get("action_category") or "").lower()
        if category in ACTION_CATEGORIES:
            return category
        return "read_only"
    if tool_name in SYSTEM_SENSITIVE_TOOLS:
        return "system_sensitive"
    if tool_name == "git_push" or "git push" in command:
        return "external_side_effect"
    if tool_name == "run_shell":
        if any(fragment in command for fragment in ("curl ", "wget ", "invoke-webrequest", " iwr ", "http://", "https://")):
            return "external_side_effect"
        if any(fragment in command for fragment in ("del ", "erase ", "rmdir ", "rm ", "remove-item", "move ")):
            return "destructive_write"
        if any(fragment in command for fragment in ("npm install", "pip install", "npm run", "pytest", "python ", "py ", "git add", "git commit")):
            return "reversible_write"
        return "read_only"
    if tool_name in READ_ONLY_TOOLS:
        return "read_only"
    if tool_name in REVERSIBLE_WRITE_TOOLS:
        return "reversible_write"
    if tool_name in DESTRUCTIVE_WRITE_TOOLS:
        return "destructive_write"
    if tool_name in EXTERNAL_SIDE_EFFECT_TOOLS:
        return "external_side_effect"
    return "system_sensitive" if score_risk(tool_name, args).level == "critical" else "read_only"


def extract_resource(config: OmegaConfig, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    args = arguments or {}
    if tool_name == "invoke_connector_operation":
        return str(args.get("resource") or args.get("base_url") or args.get("connector_id") or "")
    if tool_name in {"move_file", "copy_file"}:
        return str(args.get("destination_path") or args.get("source_path") or args.get("path") or "")
    if tool_name == "run_shell":
        return str(args.get("cwd") or ".")
    return str(args.get("relative_path") or args.get("path") or args.get("resource") or "")


def is_workspace_resource(config: OmegaConfig, tool_name: str, arguments: dict[str, Any] | None = None) -> bool:
    resource = extract_resource(config, tool_name, arguments)
    if tool_name == "invoke_connector_operation":
        category = str((arguments or {}).get("action_category") or "read_only")
        source_trust = str((arguments or {}).get("source_trust") or "local")
        if category in {"read_only", "external_side_effect"} and source_trust in {"builtin", "local"}:
            return True
    if tool_name == "run_shell" and not resource:
        return True
    try:
        safe_path(config, resource or ".")
        if tool_name in {"move_file", "copy_file"}:
            safe_path(config, str((arguments or {}).get("source_path") or ""))
        return True
    except Exception:
        return False


def rule_matches(rule: PolicyRule, context: dict[str, Any]) -> bool:
    if not rule.enabled:
        return False
    if rule.action_type and rule.action_type != context.get("action_type"):
        return False
    if rule.tool_name and rule.tool_name != context.get("tool_name"):
        return False
    if rule.resource_pattern:
        resource = str(context.get("resource") or "")
        if not fnmatch.fnmatch(resource.replace("\\", "/"), rule.resource_pattern.replace("\\", "/")):
            return False
    if rule.risk_level_min and RISK_ORDER.get(str(context.get("risk_level") or "low"), 0) < RISK_ORDER.get(rule.risk_level_min, 0):
        return False
    return _conditions_match(rule.conditions, context)


def normalize_conditions(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return redact(value)
    if isinstance(value, str):
        try:
            payload = json.loads(value)
            return redact(payload if isinstance(payload, dict) else {})
        except json.JSONDecodeError:
            return {}
    return {}


def _conditions_match(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    for key, expected in conditions.items():
        if key == "command_contains":
            command = str(context.get("command") or "").lower()
            values = expected if isinstance(expected, list) else [expected]
            if not any(str(value).lower() in command for value in values):
                return False
        elif key in {"file_count_gt", "file_count_min"}:
            if int(context.get("file_count") or 0) <= int(expected):
                return False
        elif key == "file_count_gte":
            if int(context.get("file_count") or 0) < int(expected):
                return False
        elif key == "path_in_workspace":
            if bool(context.get("path_in_workspace")) is not bool(expected):
                return False
        elif key == "action_category":
            values = expected if isinstance(expected, list) else [expected]
            if context.get("action_category") not in set(values):
                return False
        elif key == "tool_name":
            values = expected if isinstance(expected, list) else [expected]
            if context.get("tool_name") not in set(values):
                return False
        else:
            actual = context.get(key)
            values = expected if isinstance(expected, list) else [expected]
            if actual not in set(values):
                return False
    return True


def risk_max(left: str, right: str) -> str:
    return left if RISK_ORDER.get(left, 0) >= RISK_ORDER.get(right, 0) else right


def workspace_relative_or_raw(config: OmegaConfig, value: str) -> str:
    if not value:
        return ""
    try:
        path = safe_path(config, value)
        return str(path.relative_to(config.workspace.resolve())).replace("\\", "/")
    except Exception:
        return value.replace("\\", "/")
