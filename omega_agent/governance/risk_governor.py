from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_models import BudgetDecision
from omega_agent.governance.budgets import ACTION_CATEGORY_DEFAULTS
from omega_agent.runtime.events import EventsStore
from omega_agent.security.risk import risk_level_score


class RiskGovernor:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def evaluate(
        self,
        *,
        risk_level: str,
        action_category: str,
        max_risk_level: str | None,
        category_rules: dict[str, str] | None = None,
        approval_granted: bool = False,
        context=None,
        emit_events: bool = True,
    ) -> BudgetDecision:
        if not self.config.governance_risk_governor_enabled:
            return BudgetDecision("allow", "Risk Governor disabled.", risk_level=risk_level)
        max_risk = max_risk_level or self.config.governance_risk_governor_default_max_risk
        category_rule = (category_rules or {}).get(action_category) or ACTION_CATEGORY_DEFAULTS.get(action_category, "allow")
        if action_category == "system_sensitive":
            return self._decision("deny", "System-sensitive action denied by default.", risk_level, context, emit_events)
        if risk_level_score(risk_level) > risk_level_score(max_risk):
            action = "deny" if risk_level == "critical" else "require_approval"
            if approval_granted and action == "require_approval":
                return BudgetDecision("allow", "Risk approval already granted.", risk_level=risk_level)
            return self._decision(action, f"Action risk {risk_level} exceeds maximum {max_risk}.", risk_level, context, emit_events)
        if category_rule == "deny":
            return self._decision("deny", f"Action category {action_category} denied by Risk Governor.", risk_level, context, emit_events)
        if category_rule == "approval_required" and not approval_granted:
            return self._decision("require_approval", f"Action category {action_category} requires approval.", risk_level, context, emit_events)
        return BudgetDecision("allow", "Risk within effective limit.", risk_level=risk_level)

    def _decision(self, action: str, reason: str, risk_level: str, context, emit_events: bool = True) -> BudgetDecision:
        event_type = "risk.blocked" if action == "deny" else "risk.approval_required"
        if emit_events:
            self.events.add(
                event_type,
                {
                    "run_id": getattr(context, "run_id", None),
                    "workflow_run_id": getattr(context, "workflow_run_id", None),
                    "risk_level": risk_level,
                    "reason": reason,
                },
                session_id=getattr(context, "session_id", None),
            )
        return BudgetDecision(action, reason, risk_level=risk_level)
