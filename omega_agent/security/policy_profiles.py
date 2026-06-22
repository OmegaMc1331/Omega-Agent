from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.policy_rules import POLICY_EFFECTS, PolicyRule, normalize_conditions
from omega_agent.security.redaction import redact

SCOPE_TYPES = {"global", "project", "session", "agent_profile"}


@dataclass(frozen=True)
class PolicyProfile:
    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    scope_type: str
    scope_id: str | None
    default_action: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(
            {
                "id": self.id,
                "name": self.name,
                "description": self.description,
                "enabled": self.enabled,
                "priority": self.priority,
                "scope_type": self.scope_type,
                "scope_id": self.scope_id,
                "default_action": self.default_action,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "metadata": self.metadata,
            }
        )


class PolicyProfilesStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass
        self.ensure_builtin_profiles()

    def ensure_builtin_profiles(self) -> None:
        now = _now()
        with connect_runtime_db(self.config) as conn:
            for profile in _builtin_profiles(now):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO policy_profiles(
                        id, name, description, enabled, priority, scope_type, scope_id,
                        default_action, created_at, updated_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile["id"],
                        profile["name"],
                        profile["description"],
                        int(profile["enabled"]),
                        profile["priority"],
                        profile["scope_type"],
                        profile.get("scope_id"),
                        profile["default_action"],
                        now,
                        now,
                        json.dumps(profile.get("metadata") or {"builtin": True}, ensure_ascii=False),
                    ),
                )
            for rule in _builtin_rules(now):
                conn.execute(
                    """
                    INSERT INTO policy_rules(
                        id, profile_id, name, description, enabled, priority, effect,
                        action_type, tool_name, resource_pattern, risk_level_min,
                        conditions_json, reason, created_at, updated_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        profile_id = excluded.profile_id,
                        name = excluded.name,
                        description = excluded.description,
                        priority = excluded.priority,
                        effect = excluded.effect,
                        action_type = excluded.action_type,
                        tool_name = excluded.tool_name,
                        resource_pattern = excluded.resource_pattern,
                        risk_level_min = excluded.risk_level_min,
                        conditions_json = excluded.conditions_json,
                        reason = excluded.reason,
                        updated_at = excluded.updated_at,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        rule["id"],
                        rule["profile_id"],
                        rule["name"],
                        rule.get("description", ""),
                        int(rule.get("enabled", True)),
                        rule.get("priority", 0),
                        rule["effect"],
                        rule.get("action_type"),
                        rule.get("tool_name"),
                        rule.get("resource_pattern"),
                        rule.get("risk_level_min"),
                        json.dumps(rule.get("conditions") or {}, ensure_ascii=False),
                        rule.get("reason", ""),
                        now,
                        now,
                        json.dumps(rule.get("metadata") or {"builtin": True}, ensure_ascii=False),
                    ),
                )

    def list(self, include_disabled: bool = True) -> list[PolicyProfile]:
        sql = "SELECT * FROM policy_profiles"
        params: list[Any] = []
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY priority DESC, updated_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_profile_from_row(row) for row in rows]

    def get(self, profile_id: str) -> PolicyProfile | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM policy_profiles WHERE id = ?", (profile_id,)).fetchone()
        return _profile_from_row(row) if row else None

    def create(
        self,
        *,
        name: str,
        description: str = "",
        enabled: bool = True,
        priority: int = 0,
        scope_type: str = "global",
        scope_id: str | None = None,
        default_action: str = "require_approval",
        metadata: dict[str, Any] | None = None,
    ) -> PolicyProfile:
        if scope_type not in SCOPE_TYPES:
            raise ValueError("scope_type invalide.")
        if default_action not in POLICY_EFFECTS:
            raise ValueError("default_action invalide.")
        profile_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO policy_profiles(id, name, description, enabled, priority, scope_type, scope_id, default_action, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    redact(name),
                    redact(description),
                    int(enabled),
                    int(priority),
                    scope_type,
                    scope_id,
                    default_action,
                    now,
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        return self.get(profile_id)

    def patch(self, profile_id: str, updates: dict[str, Any]) -> PolicyProfile:
        current = self.get(profile_id)
        if current is None:
            raise ValueError("Policy profile introuvable.")
        allowed = {"name", "description", "enabled", "priority", "scope_type", "scope_id", "default_action", "metadata"}
        fields: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            column = "metadata_json" if key == "metadata" else key
            if key == "scope_type" and value not in SCOPE_TYPES:
                raise ValueError("scope_type invalide.")
            if key == "default_action" and value not in POLICY_EFFECTS:
                raise ValueError("default_action invalide.")
            fields.append(f"{column} = ?")
            if key == "metadata":
                params.append(json.dumps(redact(value or {}), ensure_ascii=False))
            elif key == "enabled":
                params.append(int(bool(value)))
            elif key == "priority":
                params.append(int(value))
            else:
                params.append(redact(value) if isinstance(value, str) else value)
        if not fields:
            return current
        fields.append("updated_at = ?")
        params.append(_now())
        params.append(profile_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE policy_profiles SET {', '.join(fields)} WHERE id = ?", tuple(params))
        return self.get(profile_id)

    def delete(self, profile_id: str) -> None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT metadata_json FROM policy_profiles WHERE id = ?", (profile_id,)).fetchone()
            if row:
                metadata = json.loads(row["metadata_json"] or "{}")
                if metadata.get("builtin"):
                    conn.execute("UPDATE policy_profiles SET enabled = 0, updated_at = ? WHERE id = ?", (_now(), profile_id))
                    return
            conn.execute("DELETE FROM policy_profiles WHERE id = ?", (profile_id,))


class PolicyRulesStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        PolicyProfilesStore(config).ensure_builtin_profiles()

    def list(self, profile_id: str | None = None, include_disabled: bool = True) -> list[PolicyRule]:
        sql = "SELECT * FROM policy_rules"
        clauses: list[str] = []
        params: list[Any] = []
        if profile_id:
            clauses.append("profile_id = ?")
            params.append(profile_id)
        if not include_disabled:
            clauses.append("enabled = 1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority DESC, updated_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_rule_from_row(row) for row in rows]

    def create(
        self,
        *,
        profile_id: str,
        name: str,
        effect: str,
        description: str = "",
        enabled: bool = True,
        priority: int = 0,
        action_type: str | None = None,
        tool_name: str | None = None,
        resource_pattern: str | None = None,
        risk_level_min: str | None = None,
        conditions: dict[str, Any] | None = None,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PolicyRule:
        if effect not in POLICY_EFFECTS:
            raise ValueError("Effect policy invalide.")
        if PolicyProfilesStore(self.config).get(profile_id) is None:
            raise ValueError("Policy profile introuvable.")
        rule_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO policy_rules(
                    id, profile_id, name, description, enabled, priority, effect,
                    action_type, tool_name, resource_pattern, risk_level_min,
                    conditions_json, reason, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    profile_id,
                    redact(name),
                    redact(description),
                    int(enabled),
                    int(priority),
                    effect,
                    action_type,
                    tool_name,
                    resource_pattern,
                    risk_level_min,
                    json.dumps(normalize_conditions(conditions), ensure_ascii=False),
                    redact(reason),
                    now,
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        return self.get(rule_id)

    def get(self, rule_id: str) -> PolicyRule | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM policy_rules WHERE id = ?", (rule_id,)).fetchone()
        return _rule_from_row(row) if row else None

    def patch(self, rule_id: str, updates: dict[str, Any]) -> PolicyRule:
        current = self.get(rule_id)
        if current is None:
            raise ValueError("Policy rule introuvable.")
        allowed = {
            "profile_id",
            "name",
            "description",
            "enabled",
            "priority",
            "effect",
            "action_type",
            "tool_name",
            "resource_pattern",
            "risk_level_min",
            "conditions",
            "reason",
            "metadata",
        }
        fields: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            column = "conditions_json" if key == "conditions" else "metadata_json" if key == "metadata" else key
            if key == "effect" and value not in POLICY_EFFECTS:
                raise ValueError("Effect policy invalide.")
            fields.append(f"{column} = ?")
            if key == "conditions":
                params.append(json.dumps(normalize_conditions(value), ensure_ascii=False))
            elif key == "metadata":
                params.append(json.dumps(redact(value or {}), ensure_ascii=False))
            elif key == "enabled":
                params.append(int(bool(value)))
            elif key == "priority":
                params.append(int(value))
            else:
                params.append(redact(value) if isinstance(value, str) else value)
        if not fields:
            return current
        fields.append("updated_at = ?")
        params.append(_now())
        params.append(rule_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE policy_rules SET {', '.join(fields)} WHERE id = ?", tuple(params))
        return self.get(rule_id)

    def delete(self, rule_id: str) -> None:
        with connect_runtime_db(self.config) as conn:
            conn.execute("DELETE FROM policy_rules WHERE id = ?", (rule_id,))


def _profile_from_row(row) -> PolicyProfile:
    metadata = _json(row["metadata_json"], {})
    return PolicyProfile(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        enabled=bool(row["enabled"]),
        priority=int(row["priority"]),
        scope_type=row["scope_type"],
        scope_id=row["scope_id"],
        default_action=row["default_action"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=metadata,
    )


def _rule_from_row(row) -> PolicyRule:
    return PolicyRule(
        id=row["id"],
        profile_id=row["profile_id"],
        name=row["name"],
        description=row["description"],
        enabled=bool(row["enabled"]),
        priority=int(row["priority"]),
        effect=row["effect"],
        action_type=row["action_type"],
        tool_name=row["tool_name"],
        resource_pattern=row["resource_pattern"],
        risk_level_min=row["risk_level_min"],
        conditions=_json(row["conditions_json"], {}),
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_json(row["metadata_json"], {}),
    )


def _json(value: str | None, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _builtin_profiles(now: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "local-safe",
            "name": "Local Safe",
            "description": "Workspace local avec refus hors workspace et approval pour effets externes.",
            "enabled": True,
            "priority": 10,
            "scope_type": "global",
            "default_action": "require_approval",
            "metadata": {"builtin": True},
        },
        {
            "id": "strict",
            "name": "Strict",
            "description": "Read-only par defaut, approval pour ecritures, shell dangereux refuse.",
            "enabled": False,
            "priority": 50,
            "scope_type": "global",
            "default_action": "deny",
            "metadata": {"builtin": True},
        },
        {
            "id": "developer-workspace",
            "name": "Developer Workspace",
            "description": "Autorise les ecritures et tests dans le workspace, refuse git push.",
            "enabled": True,
            "priority": 20,
            "scope_type": "global",
            "default_action": "allow",
            "metadata": {"builtin": True},
        },
        {
            "id": "mobile-access",
            "name": "Mobile Access",
            "description": "Plus strict pour les actions destructrices depuis mobile.",
            "enabled": True,
            "priority": 60,
            "scope_type": "global",
            "default_action": "require_approval",
            "metadata": {"builtin": True},
        },
        {
            "id": "untrusted-channel",
            "name": "Untrusted Channel",
            "description": "Read-only ou refus pour sources non fiables.",
            "enabled": True,
            "priority": 70,
            "scope_type": "global",
            "default_action": "require_approval",
            "metadata": {"builtin": True},
        },
    ]


def _builtin_rules(now: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "builtin-deny-system-sensitive",
            "profile_id": "local-safe",
            "name": "Deny system sensitive",
            "priority": 1000,
            "effect": "deny",
            "conditions": {"action_category": "system_sensitive"},
            "reason": "Action system-sensitive refusee par defaut.",
        },
        {
            "id": "builtin-approval-external-side-effects",
            "profile_id": "local-safe",
            "name": "Approval external side effects",
            "priority": 900,
            "effect": "require_approval",
            "conditions": {"action_category": "external_side_effect"},
            "reason": "Effet externe: confirmation requise.",
        },
        {
            "id": "builtin-bulk-delete-approval",
            "profile_id": "local-safe",
            "name": "Approval delete over 10 files",
            "priority": 850,
            "effect": "require_approval",
            "conditions": {"action_category": "destructive_write", "file_count_gt": 10},
            "reason": "Suppression de plus de 10 fichiers: confirmation requise.",
        },
        {
            "id": "builtin-developer-deny-git-push",
            "profile_id": "developer-workspace",
            "name": "Deny git push",
            "priority": 1000,
            "effect": "deny",
            "conditions": {"command_contains": "git push"},
            "reason": "git push est refuse automatiquement.",
        },
        {
            "id": "builtin-developer-allow-read",
            "profile_id": "developer-workspace",
            "name": "Allow read-only",
            "priority": 200,
            "effect": "allow",
            "conditions": {"action_category": "read_only", "workspace_full_access": True},
            "reason": "Lecture workspace autorisee.",
        },
        {
            "id": "builtin-developer-allow-writes",
            "profile_id": "developer-workspace",
            "name": "Allow reversible writes",
            "priority": 190,
            "effect": "allow",
            "conditions": {"action_category": "reversible_write", "path_in_workspace": True, "workspace_full_access": True},
            "reason": "Ecriture reversible dans le workspace autorisee.",
        },
        {
            "id": "builtin-mobile-destructive-approval",
            "profile_id": "mobile-access",
            "name": "Mobile destructive approval",
            "priority": 1000,
            "effect": "require_approval",
            "conditions": {"channel": "mobile", "action_category": "destructive_write"},
            "reason": "Action destructive depuis mobile: confirmation requise.",
        },
        {
            "id": "builtin-untrusted-deny-shell",
            "profile_id": "untrusted-channel",
            "name": "Untrusted shell denied",
            "priority": 1000,
            "effect": "deny",
            "tool_name": "run_shell",
            "conditions": {"source_trust": "untrusted"},
            "reason": "Shell refuse pour source untrusted.",
        },
        {
            "id": "builtin-untrusted-deny-destructive",
            "profile_id": "untrusted-channel",
            "name": "Untrusted destructive denied",
            "priority": 950,
            "effect": "deny",
            "conditions": {"source_trust": "untrusted", "action_category": "destructive_write"},
            "reason": "Action destructive refusee pour source untrusted.",
        },
    ]
