from __future__ import annotations

from dataclasses import dataclass

from omega_agent.config import OmegaConfig


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class CapabilityPolicyDecision:
    allowed: bool
    reason: str


class CapabilityPolicy:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def is_allowed_for_context(self, capability, *, agent_profile=None, project_scopes: set[str] | None = None) -> CapabilityPolicyDecision:
        if not capability.enabled:
            return CapabilityPolicyDecision(False, "capability disabled")
        if not capability.available:
            return CapabilityPolicyDecision(False, "capability unavailable")
        if capability.requires_auth and capability.auth_status != "configured":
            return CapabilityPolicyDecision(False, "auth missing")
        if capability.owner == "untrusted" and self.config.capabilities_untrusted_disabled_by_default:
            return CapabilityPolicyDecision(False, "untrusted disabled by default")
        if capability.risk_level == "critical" and not capability.requires_approval_default:
            return CapabilityPolicyDecision(False, "critical capability requires approval default")
        if project_scopes and capability.scopes:
            allowed_scopes = project_scopes | {"workspace", "session", "manifest", "model", "provider", "channel", "connector", "api", "openapi", "local_http", "github", "mcp"}
            if not set(capability.scopes).intersection(allowed_scopes):
                return CapabilityPolicyDecision(False, "scope not allowed")
        if agent_profile is not None:
            if capability.type == "tool" and agent_profile.allowed_tools:
                tool_id = capability.id.split(":", 1)[1] if ":" in capability.id else capability.id
                if tool_id not in agent_profile.allowed_tools:
                    return CapabilityPolicyDecision(False, "tool not allowed by agent profile")
            if capability.type == "skill" and agent_profile.allowed_skills:
                skill_id = capability.id.split(":", 1)[1] if ":" in capability.id else capability.id
                if skill_id not in agent_profile.allowed_skills:
                    return CapabilityPolicyDecision(False, "skill not allowed by agent profile")
        return CapabilityPolicyDecision(True, "allowed")


def risk_rank(value: str) -> int:
    return RISK_ORDER.get(str(value or "medium"), 1)
