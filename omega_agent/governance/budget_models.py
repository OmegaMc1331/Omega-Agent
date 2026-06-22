from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from omega_agent.security.redaction import redact

BUDGET_METRICS = {
    "max_run_seconds",
    "max_tool_calls",
    "max_actions",
    "max_shell_commands",
    "max_files_changed",
    "max_files_deleted",
    "max_rollbacks",
    "max_retries",
    "max_external_calls",
    "max_connector_calls",
    "max_estimated_cost",
    "max_estimated_tokens",
}
SCOPE_TYPES = {"global", "project", "session", "agent_profile", "workflow"}
USAGE_STATUSES = {"ok", "warning", "exceeded"}
VIOLATION_ACTIONS = {"warned", "paused", "denied", "cancelled", "approval_required"}
RISK_LEVELS = {"low", "medium", "high", "critical"}


def parse_json(value: str | None, default):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


@dataclass(frozen=True)
class BudgetProfile:
    id: str
    name: str
    description: str
    enabled: bool
    scope_type: str
    scope_id: str | None
    limits: dict[str, Any]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class BudgetUsage:
    id: str
    profile_id: str | None
    run_id: str | None
    workflow_run_id: str | None
    session_id: str | None
    project_id: str | None
    metric: str
    used_value: float
    limit_value: float | None
    status: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class BudgetViolation:
    id: str
    run_id: str | None
    workflow_run_id: str | None
    profile_id: str | None
    metric: str
    used_value: float
    limit_value: float
    action_taken: str
    reason: str
    created_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass
class BudgetContext:
    run_id: str | None = None
    workflow_run_id: str | None = None
    workflow_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    agent_profile_id: str | None = None
    provider_id: str | None = None
    connector_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class EffectiveBudget:
    limits: dict[str, Any]
    profile_ids: list[str]
    profile_names: list[str]
    limiting_profiles: dict[str, str]
    context: BudgetContext

    def as_api(self) -> dict[str, Any]:
        return redact(
            {
                "limits": self.limits,
                "profile_ids": self.profile_ids,
                "profile_names": self.profile_names,
                "limiting_profiles": self.limiting_profiles,
                "context": self.context.as_api(),
            }
        )


@dataclass(frozen=True)
class BudgetDecision:
    action: str
    reason: str
    metric: str | None = None
    used_value: float | None = None
    limit_value: float | None = None
    risk_level: str = "low"
    warnings: list[str] = field(default_factory=list)
    usage_projection: dict[str, float] = field(default_factory=dict)
    effective_budget: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.action in {"allow", "warn"}

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))
