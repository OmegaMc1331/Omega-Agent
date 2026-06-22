from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_models import BudgetProfile, BudgetViolation, SCOPE_TYPES, VIOLATION_ACTIONS, parse_json
from omega_agent.governance.budgets import ACTION_CATEGORY_DEFAULTS, DEFAULT_BUDGET_PROFILES, NUMERIC_LIMITS
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class BudgetStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass
        self.ensure_default_profiles()

    def ensure_default_profiles(self) -> None:
        now = _now()
        with connect_runtime_db(self.config) as conn:
            for item in DEFAULT_BUDGET_PROFILES:
                conn.execute(
                    """
                    INSERT INTO budget_profiles(
                        id, name, description, enabled, scope_type, scope_id,
                        limits_json, created_at, updated_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        item["id"],
                        item["name"],
                        item["description"],
                        1 if item["enabled"] else 0,
                        item["scope_type"],
                        item["scope_id"],
                        _json(item["limits"]),
                        now,
                        now,
                        _json({"builtin": True}),
                    ),
                )

    def create_profile(
        self,
        *,
        name: str,
        description: str = "",
        enabled: bool = True,
        scope_type: str = "global",
        scope_id: str | None = None,
        limits: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetProfile:
        if scope_type not in SCOPE_TYPES:
            raise ValueError("Scope budget invalide.")
        clean_limits = _validate_limits(limits or {})
        now = _now()
        profile_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO budget_profiles(
                    id, name, description, enabled, scope_type, scope_id,
                    limits_json, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, name[:160], description[:2000], 1 if enabled else 0, scope_type, scope_id, _json(clean_limits), now, now, _json(metadata or {})),
            )
        return self.get_profile(profile_id)

    def get_profile(self, profile_id_or_name: str) -> BudgetProfile | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM budget_profiles WHERE id = ? OR lower(name) = lower(?) ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END LIMIT 1",
                (profile_id_or_name, profile_id_or_name, profile_id_or_name),
            ).fetchone()
        return _profile(row) if row else None

    def list_profiles(self, *, enabled: bool | None = None) -> list[BudgetProfile]:
        query = "SELECT * FROM budget_profiles"
        params: list[Any] = []
        if enabled is not None:
            query += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        query += " ORDER BY name"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_profile(row) for row in rows]

    def update_profile(self, profile_id: str, patch: dict[str, Any]) -> BudgetProfile | None:
        current = self.get_profile(profile_id)
        if current is None:
            return None
        scope_type = str(patch.get("scope_type") or current.scope_type)
        if scope_type not in SCOPE_TYPES:
            raise ValueError("Scope budget invalide.")
        limits = _validate_limits(patch.get("limits") if isinstance(patch.get("limits"), dict) else current.limits)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE budget_profiles SET name=?, description=?, enabled=?, scope_type=?,
                    scope_id=?, limits_json=?, updated_at=?, metadata_json=? WHERE id=?
                """,
                (
                    str(patch.get("name") or current.name)[:160],
                    str(patch.get("description") if patch.get("description") is not None else current.description)[:2000],
                    1 if bool(patch.get("enabled", current.enabled)) else 0,
                    scope_type,
                    patch.get("scope_id", current.scope_id),
                    _json(limits),
                    _now(),
                    _json(patch.get("metadata") if isinstance(patch.get("metadata"), dict) else current.metadata),
                    current.id,
                ),
            )
        return self.get_profile(current.id)

    def delete_profile(self, profile_id: str) -> bool:
        profile = self.get_profile(profile_id)
        if profile is None:
            return False
        if profile.metadata.get("builtin"):
            self.update_profile(profile_id, {"enabled": False})
            return True
        with connect_runtime_db(self.config) as conn:
            return conn.execute("DELETE FROM budget_profiles WHERE id = ?", (profile_id,)).rowcount > 0

    def matching_profiles(self, context) -> list[BudgetProfile]:
        default = self.get_profile(self.config.governance_budgets_default_profile)
        profiles = []
        if default and default.enabled:
            profiles.append(default)
        for profile in self.list_profiles(enabled=True):
            if default and profile.id == default.id:
                continue
            if profile.scope_type == "global":
                profiles.append(profile)
            elif profile.scope_type == "project" and profile.scope_id == context.project_id:
                profiles.append(profile)
            elif profile.scope_type == "session" and profile.scope_id == context.session_id:
                profiles.append(profile)
            elif profile.scope_type == "agent_profile" and profile.scope_id == context.agent_profile_id:
                profiles.append(profile)
            elif profile.scope_type == "workflow" and profile.scope_id in {context.workflow_id, context.workflow_run_id}:
                profiles.append(profile)
        return profiles

    def create_violation(
        self,
        *,
        run_id: str | None,
        workflow_run_id: str | None,
        profile_id: str | None,
        metric: str,
        used_value: float,
        limit_value: float,
        action_taken: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetViolation:
        if action_taken not in VIOLATION_ACTIONS:
            raise ValueError("Action violation invalide.")
        violation_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO budget_violations(
                    id, run_id, workflow_run_id, profile_id, metric, used_value,
                    limit_value, action_taken, reason, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (violation_id, run_id, workflow_run_id, profile_id, metric, used_value, limit_value, action_taken, reason[:2000], _now(), _json(metadata or {})),
            )
        return self.get_violation(violation_id)

    def get_violation(self, violation_id: str) -> BudgetViolation | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM budget_violations WHERE id = ?", (violation_id,)).fetchone()
        return _violation(row) if row else None

    def list_violations(self, *, run_id: str | None = None, workflow_run_id: str | None = None, limit: int = 200) -> list[BudgetViolation]:
        query = "SELECT * FROM budget_violations"
        clauses = []
        params: list[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if workflow_run_id:
            clauses.append("workflow_run_id = ?")
            params.append(workflow_run_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_violation(row) for row in rows]


def _profile(row) -> BudgetProfile:
    return BudgetProfile(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        enabled=bool(row["enabled"]),
        scope_type=row["scope_type"],
        scope_id=row["scope_id"],
        limits=parse_json(row["limits_json"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _violation(row) -> BudgetViolation:
    return BudgetViolation(
        id=row["id"],
        run_id=row["run_id"],
        workflow_run_id=row["workflow_run_id"],
        profile_id=row["profile_id"],
        metric=row["metric"],
        used_value=float(row["used_value"]),
        limit_value=float(row["limit_value"]),
        action_taken=row["action_taken"],
        reason=row["reason"],
        created_at=row["created_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _json(value: Any) -> str:
    return json.dumps(redact(value), ensure_ascii=False)


def _validate_limits(limits: dict[str, Any]) -> dict[str, Any]:
    if redact(limits) != limits:
        raise ValueError("Secret refuse dans les limites budget.")
    result = dict(limits)
    for key in NUMERIC_LIMITS:
        if key not in result or result[key] is None:
            continue
        try:
            value = float(result[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Limite numerique invalide: {key}") from exc
        if value < 0:
            raise ValueError(f"Limite negative refusee: {key}")
        result[key] = value
    if "max_risk_level" in result and str(result["max_risk_level"]) not in {"low", "medium", "high", "critical"}:
        raise ValueError("max_risk_level invalide.")
    for category in ACTION_CATEGORY_DEFAULTS:
        if category in result and str(result[category]) not in {"allow", "approval_required", "deny"}:
            raise ValueError(f"Action budget invalide pour {category}.")
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
