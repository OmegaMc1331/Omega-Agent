from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_models import BudgetContext, BudgetDecision, EffectiveBudget
from omega_agent.governance.budget_store import BudgetStore
from omega_agent.governance.budgets import ACTION_CATEGORY_DEFAULTS, NUMERIC_LIMITS
from omega_agent.governance.quota_tracker import QuotaTracker
from omega_agent.governance.risk_governor import RiskGovernor
from omega_agent.runtime.action_journal import classify_action, snapshot_paths_for_tool, tool_modifies_files
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.risk import risk_level_score, score_risk


class BudgetEnforcer:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = BudgetStore(config)
        self.tracker = QuotaTracker(config)
        self.risk = RiskGovernor(config)
        self.events = EventsStore(config)

    def context(self, **values) -> BudgetContext:
        context = BudgetContext(**values)
        with connect_runtime_db(self.config) as conn:
            if context.run_id:
                run = conn.execute("SELECT * FROM runs WHERE id = ?", (context.run_id,)).fetchone()
                if run:
                    context.session_id = context.session_id or run["session_id"]
                    context.project_id = context.project_id or run["project_id"]
                    context.agent_profile_id = context.agent_profile_id or run["active_agent_profile_id"]
            if context.workflow_run_id:
                workflow_run = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (context.workflow_run_id,)).fetchone()
                if workflow_run:
                    context.workflow_id = context.workflow_id or workflow_run["workflow_id"]
                    context.run_id = context.run_id or workflow_run["run_id"]
            elif context.run_id:
                workflow_run = conn.execute(
                    "SELECT * FROM workflow_runs WHERE run_id = ? ORDER BY updated_at DESC LIMIT 1",
                    (context.run_id,),
                ).fetchone()
                if workflow_run:
                    context.workflow_run_id = workflow_run["id"]
                    context.workflow_id = workflow_run["workflow_id"]
        return context

    def get_effective_budget(self, context: BudgetContext | dict | None = None) -> EffectiveBudget:
        if isinstance(context, dict):
            context = self.context(**context)
        context = context or self.context()
        profiles = self.store.matching_profiles(context)
        limits: dict[str, Any] = {}
        limiting: dict[str, str] = {}
        category_rules = dict(ACTION_CATEGORY_DEFAULTS)
        for profile in profiles:
            for key, value in profile.limits.items():
                if key in NUMERIC_LIMITS and value is not None:
                    number = float(value)
                    if key not in limits or number < float(limits[key]):
                        limits[key] = number
                        limiting[key] = profile.id
                elif key == "max_risk_level":
                    if key not in limits or risk_level_score(str(value)) < risk_level_score(str(limits[key])):
                        limits[key] = str(value)
                        limiting[key] = profile.id
                elif key in ACTION_CATEGORY_DEFAULTS:
                    category_rules[key] = _stricter_action(category_rules.get(key, "allow"), str(value))
                    limiting[key] = profile.id
                elif key in {"connectors", "providers"} and isinstance(value, dict):
                    limits[key] = _merge_nested_limits(limits.get(key) or {}, value)
        limits["max_run_seconds"] = min(float(limits.get("max_run_seconds", self.config.runtime_max_run_seconds)), float(self.config.runtime_max_run_seconds))
        limits["max_actions"] = min(float(limits.get("max_actions", self.config.runtime_max_actions_per_turn)), float(self.config.runtime_max_actions_per_turn))
        limits["max_retries"] = min(float(limits.get("max_retries", self.config.self_healing_max_attempts)), float(self.config.self_healing_max_attempts))
        configured_risk = self.config.governance_risk_governor_default_max_risk
        profile_risk = str(limits.get("max_risk_level") or configured_risk)
        limits["max_risk_level"] = profile_risk if risk_level_score(profile_risk) <= risk_level_score(configured_risk) else configured_risk
        limits.update(category_rules)
        return EffectiveBudget(
            limits=limits,
            profile_ids=[item.id for item in profiles],
            profile_names=[item.name for item in profiles],
            limiting_profiles=limiting,
            context=context,
        )

    def check_before_action(self, context: BudgetContext | dict, action: dict[str, Any]) -> BudgetDecision:
        if isinstance(context, dict):
            context = self.context(**context)
        effective = self.get_effective_budget(context)
        tool_name = str(action.get("tool_name") or "")
        arguments = dict(action.get("arguments") or {})
        category = str(action.get("action_category") or classify_action(tool_name, arguments))
        risk_level = str(action.get("risk_level") or score_risk(tool_name, arguments).level)
        risk_decision = self.risk.evaluate(
            risk_level=risk_level,
            action_category=category,
            max_risk_level=str(effective.limits.get("max_risk_level") or self.config.governance_risk_governor_default_max_risk),
            category_rules={key: str(effective.limits.get(key)) for key in ACTION_CATEGORY_DEFAULTS},
            approval_granted=bool(action.get("approval_granted")),
            context=context,
            emit_events=not bool(action.get("simulate")),
        )
        if risk_decision.action != "allow":
            return replace(risk_decision, effective_budget=effective.as_api())
        if not self.config.governance_budgets_enabled:
            return BudgetDecision("allow", "Budget governance disabled; risk check passed.", risk_level=risk_level, effective_budget=effective.as_api())
        duration_limit = _limit_for_metric(effective, "max_run_seconds", context)
        if duration_limit is not None:
            duration = self.current_usage(context, "max_run_seconds")
            if duration > duration_limit:
                return self._exceeded_decision(context, effective, "max_run_seconds", duration, duration_limit, category, risk_level, persist=not bool(action.get("simulate")))
        projections = self._projected_metrics(context, action)
        warnings = []
        for metric, increment in projections.items():
            limit = _limit_for_metric(effective, metric, context)
            if limit is None:
                continue
            current = self.current_usage(context, metric)
            projected = current + increment
            if projected > limit:
                return self._exceeded_decision(context, effective, metric, projected, limit, category, risk_level, persist=not bool(action.get("simulate")))
            if limit > 0 and projected >= limit * self.config.governance_budgets_warning_threshold:
                warnings.append(f"{metric}: {projected:g}/{limit:g}")
        if warnings:
            return BudgetDecision(
                "warn",
                "Budget warning threshold reached.",
                risk_level=risk_level,
                warnings=warnings,
                usage_projection=projections,
                effective_budget=effective.as_api(),
            )
        return BudgetDecision("allow", "Within effective budget.", risk_level=risk_level, usage_projection=projections, effective_budget=effective.as_api())

    def record_usage(self, context: BudgetContext | dict, metric: str, increment: float, *, metadata: dict[str, Any] | None = None):
        if isinstance(context, dict):
            context = self.context(**context)
        if not self.config.governance_budgets_enabled or not self.config.governance_budgets_enforce:
            return BudgetDecision(
                "allow",
                f"Budget enforcement disabled for {metric}.",
                metric=metric,
                risk_level="low",
            )
        effective = self.get_effective_budget(context)
        return self.tracker.record(context, metric, increment, effective, metadata=metadata)

    def check_metric(
        self,
        context: BudgetContext | dict,
        metric: str,
        increment: float = 1,
        *,
        action_category: str = "read_only",
        risk_level: str = "low",
    ) -> BudgetDecision:
        if isinstance(context, dict):
            context = self.context(**context)
        effective = self.get_effective_budget(context)
        limit = _limit_for_metric(effective, metric, context)
        if limit is None:
            return BudgetDecision("allow", f"No limit configured for {metric}.", risk_level=risk_level)
        projected = self.current_usage(context, metric) + float(increment)
        if projected > limit:
            return self._exceeded_decision(context, effective, metric, projected, limit, action_category, risk_level)
        if limit > 0 and projected >= limit * self.config.governance_budgets_warning_threshold:
            return BudgetDecision("warn", f"Budget warning for {metric}: {projected:g}/{limit:g}.", metric=metric, used_value=projected, limit_value=limit, risk_level=risk_level)
        return BudgetDecision("allow", f"Within {metric} budget.", metric=metric, used_value=projected, limit_value=limit, risk_level=risk_level)

    def record_action_usage(self, context: BudgetContext | dict, action: dict[str, Any], result: Any = None) -> list:
        if isinstance(context, dict):
            context = self.context(**context)
        effective = self.get_effective_budget(context)
        records = []
        for metric, increment in self._projected_metrics(context, action).items():
            records.append(self.tracker.record(context, metric, increment, effective, metadata={"result_status": getattr(result, "status", None)}))
        return records

    def check_after_action(self, context: BudgetContext | dict, action: dict[str, Any], result: Any):
        return self.record_action_usage(context, action, result)

    def create_violation(self, context: BudgetContext, metric: str, used_value: float, limit_value: float, action_taken: str, reason: str, *, profile_id: str | None = None, metadata: dict | None = None):
        violation = self.store.create_violation(
            run_id=context.run_id,
            workflow_run_id=context.workflow_run_id,
            profile_id=profile_id,
            metric=metric,
            used_value=used_value,
            limit_value=limit_value,
            action_taken=action_taken,
            reason=reason,
            metadata=metadata,
        )
        self.events.add("budget.violation.created", violation.as_api(), session_id=context.session_id)
        return violation

    def should_pause_run(self, context: BudgetContext | dict) -> bool:
        if isinstance(context, dict):
            context = self.context(**context)
        return any(item.action_taken == "paused" for item in self.store.list_violations(run_id=context.run_id, workflow_run_id=context.workflow_run_id))

    def should_require_approval(self, context: BudgetContext | dict) -> bool:
        if isinstance(context, dict):
            context = self.context(**context)
        return any(item.action_taken == "approval_required" for item in self.store.list_violations(run_id=context.run_id, workflow_run_id=context.workflow_run_id))

    def should_cancel_run(self, context: BudgetContext | dict) -> bool:
        if isinstance(context, dict):
            context = self.context(**context)
        return any(item.action_taken == "cancelled" for item in self.store.list_violations(run_id=context.run_id, workflow_run_id=context.workflow_run_id))

    def current_usage(self, context: BudgetContext, metric: str) -> float:
        if metric == "max_run_seconds" and context.run_id:
            with connect_runtime_db(self.config) as conn:
                row = conn.execute("SELECT started_at FROM runs WHERE id = ?", (context.run_id,)).fetchone()
            if row and row["started_at"]:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
                except ValueError:
                    pass
        return self.tracker.get_usage_value(context, metric)

    def _projected_metrics(self, context: BudgetContext, action: dict[str, Any]) -> dict[str, float]:
        tool_name = str(action.get("tool_name") or "")
        arguments = dict(action.get("arguments") or {})
        projections: dict[str, float] = {}
        if action.get("skip_action_count"):
            pass
        elif action.get("workflow_step"):
            projections["max_actions"] = 1
        elif tool_name:
            projections["max_actions"] = 1
        if tool_name:
            projections["max_tool_calls"] = 1
        if tool_name == "run_shell":
            projections["max_shell_commands"] = 1
        if tool_modifies_files(tool_name, arguments):
            projections["max_files_changed"] = max(1, len([path for path in snapshot_paths_for_tool(tool_name, arguments) if path]))
        if tool_name in {"delete_file", "delete_directory"}:
            projections["max_files_deleted"] = 1
        category = str(action.get("action_category") or classify_action(tool_name, arguments))
        if category == "external_side_effect" or tool_name.startswith(("browser_", "desktop_")):
            projections["max_external_calls"] = 1
        if tool_name == "invoke_connector_operation":
            projections["max_connector_calls"] = 1
            connector_id = str(action.get("connector_id") or context.connector_id or arguments.get("connector_id") or "")
            if connector_id:
                projections[f"connector:{connector_id}"] = 1
                if connector_id not in {"filesystem", "memory"}:
                    projections["max_external_calls"] = projections.get("max_external_calls", 0) + 1
        if action.get("provider_id") or context.provider_id:
            projections[f"provider:{action.get('provider_id') or context.provider_id}"] = 1
            if str(action.get("provider_id") or context.provider_id) != "ollama":
                projections["max_external_calls"] = projections.get("max_external_calls", 0) + 1
        if action.get("estimated_cost") is not None:
            projections["max_estimated_cost"] = float(action.get("estimated_cost") or 0)
        if action.get("estimated_tokens") is not None:
            projections["max_estimated_tokens"] = float(action.get("estimated_tokens") or 0)
        return projections

    def _exceeded_decision(self, context: BudgetContext, effective: EffectiveBudget, metric: str, used: float, limit: float, category: str, risk_level: str, *, persist: bool = True) -> BudgetDecision:
        if category == "external_side_effect":
            action = "approval_required" if limit > 0 else "denied"
        elif category == "destructive_write":
            action = "denied"
        else:
            action = "paused"
        reason = f"Budget exceeded for {metric}: {used:g} > {limit:g}."
        profile_id = effective.limiting_profiles.get(metric)
        if persist:
            self.create_violation(context, metric, used, limit, action, reason, profile_id=profile_id, metadata={"category": category, "risk_level": risk_level})
            self.events.add("budget.exceeded", {"run_id": context.run_id, "workflow_run_id": context.workflow_run_id, "metric": metric, "used_value": used, "limit_value": limit, "action_taken": action}, session_id=context.session_id)
            event_type = "budget.action.denied" if action == "denied" else "budget.run.paused" if action == "paused" else "risk.approval_required"
            self.events.add(event_type, {"run_id": context.run_id, "workflow_run_id": context.workflow_run_id, "metric": metric, "reason": reason}, session_id=context.session_id)
        return BudgetDecision(
            "require_approval" if action == "approval_required" else "deny" if action == "denied" else "pause",
            reason,
            metric=metric,
            used_value=used,
            limit_value=limit,
            risk_level=risk_level,
            effective_budget=effective.as_api(),
        )


def _limit_for_metric(effective: EffectiveBudget, metric: str, context: BudgetContext) -> float | None:
    if metric.startswith("connector:"):
        connector_id = metric.split(":", 1)[1]
        value = ((effective.limits.get("connectors") or {}).get(connector_id) or {}).get("max_calls")
    elif metric.startswith("provider:"):
        provider_id = metric.split(":", 1)[1]
        value = ((effective.limits.get("providers") or {}).get(provider_id) or {}).get("max_calls")
    else:
        value = effective.limits.get(metric)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _stricter_action(first: str, second: str) -> str:
    rank = {"allow": 0, "warn": 1, "approval_required": 2, "deny": 3}
    return first if rank.get(first, 0) >= rank.get(second, 0) else second


def _merge_nested_limits(existing: dict, incoming: dict) -> dict:
    result = {key: dict(value) if isinstance(value, dict) else value for key, value in existing.items()}
    for key, value in incoming.items():
        if not isinstance(value, dict):
            result[key] = value
            continue
        current = dict(result.get(key) or {})
        for metric, limit in value.items():
            if metric not in current:
                current[metric] = limit
            else:
                try:
                    current[metric] = min(float(current[metric]), float(limit))
                except (TypeError, ValueError):
                    current[metric] = limit
        result[key] = current
    return result
