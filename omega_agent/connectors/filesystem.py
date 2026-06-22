from __future__ import annotations

from omega_agent.connectors.base import ConnectorOperation


def filesystem_operations(connector_id: str = "filesystem") -> list[ConnectorOperation]:
    return [
        ConnectorOperation(
            id="list_files",
            connector_id=connector_id,
            name="List workspace files",
            description="Liste les fichiers dans le workspace Omega.",
            input_schema={"type": "object", "properties": {"relative_path": {"type": "string"}}},
            risk_level="low",
            requires_approval_default=False,
            action_category="read_only",
        ),
        ConnectorOperation(
            id="read_file",
            connector_id=connector_id,
            name="Read workspace file",
            description="Lit un fichier texte dans le workspace Omega.",
            input_schema={"type": "object", "properties": {"relative_path": {"type": "string"}}},
            risk_level="medium",
            requires_approval_default=False,
            action_category="read_only",
        ),
        ConnectorOperation(
            id="write_file",
            connector_id=connector_id,
            name="Write workspace file",
            description="Ecrit un fichier dans le workspace Omega.",
            input_schema={"type": "object", "properties": {"relative_path": {"type": "string"}, "content": {"type": "string"}}},
            risk_level="high",
            requires_approval_default=True,
            action_category="reversible_write",
        ),
        ConnectorOperation(
            id="delete_file",
            connector_id=connector_id,
            name="Delete workspace file",
            description="Supprime un fichier dans le workspace Omega.",
            input_schema={"type": "object", "properties": {"relative_path": {"type": "string"}}},
            risk_level="high",
            requires_approval_default=True,
            action_category="destructive_write",
        ),
    ]
