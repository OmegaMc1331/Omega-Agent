from __future__ import annotations

from omega_agent.connectors.base import ConnectorOperation


def mcp_bridge_operations(connector_id: str = "mcp_bridge") -> list[ConnectorOperation]:
    return [
        ConnectorOperation(
            id="list_servers",
            connector_id=connector_id,
            name="List MCP server manifests",
            description="Liste les serveurs MCP declares dans Omega sans execution externe.",
            input_schema={"type": "object", "properties": {}},
            risk_level="low",
            requires_approval_default=False,
            action_category="read_only",
            enabled=True,
        )
    ]
