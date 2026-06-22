from __future__ import annotations

from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.security.risk import max_risk_level


def compute_risk_report(
    config: OmegaConfig,
    plan: dict[str, Any],
    predicted_diff: dict[str, Any],
    steps: list[dict[str, Any]],
    invariants: dict[str, Any],
) -> dict[str, Any]:
    planned_steps = plan.get("steps") or []
    files_modified = len(predicted_diff.get("created") or []) + len(predicted_diff.get("modified") or [])
    files_deleted = len(predicted_diff.get("deleted") or [])
    shell_commands = sum(1 for step in planned_steps if step.get("tool_name") == "run_shell")
    external_calls = sum(1 for step in planned_steps if step.get("action_category") == "external_side_effect")
    non_simulable = [step.get("name") for step in planned_steps if not step.get("simulable", True)]
    policy_denials = [step for step in steps if step.get("status") == "failed" and step.get("policy_denied")]
    skipped = [step for step in steps if step.get("status") == "skipped"]
    risk_levels = [str(step.get("risk_level") or "low") for step in planned_steps] or ["low"]
    risk_level = max_risk_level(*risk_levels)
    effective = BudgetEnforcer(config).get_effective_budget(BudgetEnforcer(config).context())
    estimated_usage = {
        "max_actions": len(planned_steps),
        "max_tool_calls": sum(1 for step in planned_steps if step.get("tool_name")),
        "max_shell_commands": shell_commands,
        "max_files_changed": files_modified,
        "max_files_deleted": files_deleted,
        "max_external_calls": external_calls,
    }
    exceeded = [
        metric
        for metric, used in estimated_usage.items()
        if effective.limits.get(metric) is not None and float(used) > float(effective.limits[metric])
    ]
    confidence = 0.95
    confidence -= min(0.4, len(non_simulable) * 0.2)
    confidence -= min(0.25, len(skipped) * 0.1)
    if not invariants.get("passed"):
        confidence = min(confidence, 0.2)
    if policy_denials or not invariants.get("passed"):
        recommendation = "reject"
    elif risk_level in {"high", "critical"} or external_calls or exceeded:
        recommendation = "require_approval"
    else:
        recommendation = "promote"
    return {
        "risk_level": risk_level,
        "files_modified": files_modified,
        "files_deleted": files_deleted,
        "shell_commands": shell_commands,
        "external_calls": external_calls,
        "actions_non_simulable": non_simulable,
        "policy_denials": len(policy_denials),
        "skipped_external_actions": [step.get("name") for step in skipped if step.get("action_category") == "external_side_effect"],
        "budget_usage_estimated": estimated_usage,
        "budget_limits": effective.limits,
        "budget_exceeded": exceeded,
        "rollback_available": files_modified + files_deleted > 0 and config.runtime_snapshots_enabled,
        "confidence": round(max(0.0, confidence), 2),
        "recommendation": recommendation,
        "invariants": invariants,
    }
