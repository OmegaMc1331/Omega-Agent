from __future__ import annotations

from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.connectors.registry import ConnectorsRegistry


def build_connector_policy_context(config: OmegaConfig, arguments: dict[str, Any]) -> dict[str, Any]:
    connector_id = str(arguments.get("connector_id") or "")
    operation_id = str(arguments.get("operation_id") or "")
    if not connector_id or not operation_id:
        raise ValueError("connector_id et operation_id sont requis.")
    context = ConnectorsRegistry(config).operation_policy_context(connector_id, operation_id)
    operation_args = dict(arguments.get("arguments") or {})
    enriched = dict(arguments)
    enriched["action_category"] = context["action_category"]
    enriched["risk_level"] = context["risk_level"]
    enriched["source_trust"] = context["source_trust"]
    enriched["capability_id"] = context["capability_id"]
    enriched["resource"] = context["resource"]
    enriched["operation_arguments"] = operation_args
    return {**context, "arguments": enriched}
