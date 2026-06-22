from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.policy_profiles import PolicyProfilesStore, PolicyRulesStore
from omega_agent.security.policy_rules import classify_action, extract_resource, is_workspace_resource, risk_max, rule_matches, workspace_relative_or_raw
from omega_agent.security.redaction import redact
from omega_agent.security.risk import score_risk


@dataclass(frozen=True)
class PolicySimulationResult:
    final_decision: str
    matched_rules: list[dict[str, Any]]
    risk_level: str
    reason: str
    would_create_approval: bool
    would_create_snapshot: bool
    warnings: list[str]
    action_category: str
    base_decision: dict[str, Any]
    shadow_required: bool
    shadow_reason: str | None

    def as_api(self) -> dict[str, Any]:
        return redact(
            {
                "final_decision": self.final_decision,
                "decision": self.final_decision,
                "matched_rules": self.matched_rules,
                "risk_level": self.risk_level,
                "reason": self.reason,
                "would_create_approval": self.would_create_approval,
                "would_create_snapshot": self.would_create_snapshot,
                "warnings": self.warnings,
                "action_category": self.action_category,
                "base_decision": self.base_decision,
                "shadow_required": self.shadow_required,
                "shadow_reason": self.shadow_reason,
            }
        )


class PolicySimulator:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.profiles = PolicyProfilesStore(config)
        self.rules = PolicyRulesStore(config)

    def simulate_policy(self, action_context: dict[str, Any], *, store: bool = True) -> dict[str, Any]:
        context = self.build_context(action_context)
        base = self._base_decision(context)
        matched = self._matched_rules(context)
        final, reason, warnings = self._resolve(base, matched, context)
        explicit_shadow = any(bool(rule.get("shadow_required")) for rule in matched)
        configured_shadow = bool(
            self.config.shadow_enabled
            and self.config.shadow_require_for_high_risk
            and context["action_category"] in {"destructive_write", "external_side_effect", "system_sensitive"}
        )
        shadow_required = explicit_shadow or configured_shadow
        shadow_reason = (
            "Shadow imposé par une règle policy."
            if explicit_shadow
            else "Shadow requis par configuration pour action destructive ou externe."
            if configured_shadow
            else None
        )
        result = PolicySimulationResult(
            final_decision=final,
            matched_rules=matched,
            risk_level=context["risk_level"],
            reason=reason,
            would_create_approval=final == "require_approval",
            would_create_snapshot=context["action_category"] in {"reversible_write", "destructive_write"} and context["path_in_workspace"],
            warnings=warnings,
            action_category=context["action_category"],
            base_decision=base,
            shadow_required=shadow_required,
            shadow_reason=shadow_reason,
        ).as_api()
        if store:
            self.store_simulation(action_context, result)
        return result

    def build_context(self, action_context: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(action_context.get("tool_name") or action_context.get("tool") or "")
        arguments = action_context.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if "path" in action_context and "relative_path" not in arguments:
            arguments["relative_path"] = action_context["path"]
        if "command" in action_context and "command" not in arguments:
            arguments["command"] = action_context["command"]
        action_category = str(action_context.get("action_category") or classify_action(tool_name, arguments))
        risk = str(action_context.get("risk_level") or arguments.get("risk_level") or score_risk(tool_name, arguments).level)
        if action_category == "system_sensitive":
            risk = "critical"
        resource = workspace_relative_or_raw(self.config, extract_resource(self.config, tool_name, arguments))
        path_in_workspace = is_workspace_resource(self.config, tool_name, arguments)
        return redact(
            {
                "tool_name": tool_name,
                "action_type": action_context.get("action_type") or tool_name,
                "arguments": arguments,
                "project_id": action_context.get("project_id"),
                "session_id": action_context.get("session_id"),
                "agent_profile_id": action_context.get("agent_profile_id"),
                "channel": action_context.get("channel") or "local",
                "source_trust": action_context.get("source_trust") or "local",
                "capability_id": action_context.get("capability_id") or f"tool:{tool_name}",
                "resource": resource,
                "risk_level": risk,
                "action_category": action_category,
                "file_count": int(action_context.get("file_count") or _infer_file_count(tool_name, arguments)),
                "command": str(arguments.get("command") or action_context.get("command") or ""),
                "path_in_workspace": path_in_workspace,
                "workspace_full_access": bool(self.config.workspace_full_access),
                "require_approval": bool(self.config.require_approval),
            }
        )

    def store_simulation(self, input_payload: dict[str, Any], result: dict[str, Any]) -> str:
        simulation_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO policy_simulations(id, input_json, result_json, created_at, metadata_json) VALUES (?, ?, ?, ?, '{}')",
                (
                    simulation_id,
                    json.dumps(redact(input_payload), ensure_ascii=False),
                    json.dumps(redact(result), ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return simulation_id

    def list_simulations(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM policy_simulations ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        items = []
        for row in rows:
            items.append(
                redact(
                    {
                        "id": row["id"],
                        "input": _json(row["input_json"], {}),
                        "result": _json(row["result_json"], {}),
                        "created_at": row["created_at"],
                        "metadata": _json(row["metadata_json"], {}),
                    }
                )
            )
        return items

    def _base_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        if context["tool_name"] == "invoke_connector_operation":
            category = context.get("action_category")
            if category == "system_sensitive":
                return {"action": "deny", "decision": "deny", "reason": "Operation connecteur system-sensitive refusee.", "risk_level": "critical"}
            if category in {"reversible_write", "destructive_write", "external_side_effect"}:
                return {
                    "action": "require_approval",
                    "decision": "require_approval",
                    "reason": "Operation connecteur sensible: approval requis.",
                    "risk_level": context.get("risk_level") or "high",
                }
            return {"action": "allow", "decision": "allow", "reason": "Operation connecteur read-only.", "risk_level": context.get("risk_level") or "low"}
        from omega_agent.security.policy import _base_workspace_policy_decision

        decision = _base_workspace_policy_decision(self.config, context["tool_name"], context["arguments"], require_approval=True)
        return redact(
            {
                "action": decision.action,
                "decision": decision.action,
                "reason": decision.reason,
                "risk_level": decision.risk_level,
            }
        )

    def _matched_rules(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        profiles = self.profiles.list(include_disabled=False)
        rules = self.rules.list(include_disabled=False)
        profile_map = {profile.id: profile for profile in profiles}
        matched: list[dict[str, Any]] = []
        for rule in rules:
            profile = profile_map.get(rule.profile_id)
            if profile is None or not _profile_applies(profile, context):
                continue
            if not rule_matches(rule, context):
                continue
            matched.append(
                redact(
                    {
                        "id": rule.id,
                        "profile_id": rule.profile_id,
                        "profile_name": profile.name,
                        "name": rule.name,
                        "effect": rule.effect,
                        "priority": int(profile.priority) * 10000 + int(rule.priority),
                        "rule_priority": rule.priority,
                        "profile_priority": profile.priority,
                        "reason": rule.reason or profile.description,
                        "shadow_required": bool(rule.metadata.get("shadow_required")),
                    }
                )
            )
        matched.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
        return matched

    def _resolve(self, base: dict[str, Any], matched: list[dict[str, Any]], context: dict[str, Any]) -> tuple[str, str, list[str]]:
        warnings: list[str] = []
        base_action = str(base.get("action") or "require_approval")
        base_reason = str(base.get("reason") or "")
        risk = str(base.get("risk_level") or context.get("risk_level") or "low")
        risk = risk_max(risk, context["risk_level"])
        if context["action_category"] == "system_sensitive":
            return "deny", "Action system-sensitive refusee par defaut.", ["system_sensitive denied"]
        if context["tool_name"] == "invoke_connector_operation" and context.get("source_trust") == "blocked":
            return "deny", "Connecteur blocked refuse.", ["blocked connector denied"]
        if context["tool_name"] == "invoke_connector_operation" and context.get("source_trust") == "untrusted":
            return "require_approval", "Connecteur untrusted: approval requis avant execution.", ["untrusted connector requires approval"]
        if base_action == "deny":
            return "deny", base_reason, ["hard backend policy denied"]
        if not context["path_in_workspace"] and context["tool_name"] not in {"browser_open_url", "invoke_connector_operation"}:
            return "deny", "Action hors workspace refusee.", ["outside workspace denied"]
        deny = next((rule for rule in matched if rule.get("effect") == "deny"), None)
        if deny:
            return "deny", str(deny.get("reason") or deny.get("name") or "Policy deny."), warnings
        approval = next((rule for rule in matched if rule.get("effect") == "require_approval"), None)
        if approval:
            return "require_approval", str(approval.get("reason") or approval.get("name") or "Approval requise par policy."), warnings
        allow = next((rule for rule in matched if rule.get("effect") == "allow"), None)
        if allow:
            if risk == "critical":
                return "deny", "Risque critique refuse malgre rule allow.", ["critical risk cannot be allowed"]
            return "allow", str(allow.get("reason") or allow.get("name") or "Autorise par policy."), warnings
        return base_action, base_reason or "Decision policy par defaut.", warnings


def simulate_policy(config: OmegaConfig, action_context: dict[str, Any]) -> dict[str, Any]:
    return PolicySimulator(config).simulate_policy(action_context)


def _profile_applies(profile, context: dict[str, Any]) -> bool:
    if profile.scope_type == "global":
        return True
    if profile.scope_type == "project":
        return not profile.scope_id or profile.scope_id == context.get("project_id")
    if profile.scope_type == "session":
        return not profile.scope_id or profile.scope_id == context.get("session_id")
    if profile.scope_type == "agent_profile":
        return not profile.scope_id or profile.scope_id == context.get("agent_profile_id")
    return False


def _infer_file_count(tool_name: str, arguments: dict[str, Any]) -> int:
    if "file_count" in arguments:
        return int(arguments.get("file_count") or 0)
    paths = arguments.get("paths")
    if isinstance(paths, list):
        return len(paths)
    if tool_name in {"delete_file", "write_file", "append_file", "move_file", "copy_file"}:
        return 1
    return 0


def _json(value: str | None, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
