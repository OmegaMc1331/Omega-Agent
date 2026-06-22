from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
TRUST_LEVELS = {"builtin", "local", "untrusted", "blocked"}


@dataclass(frozen=True)
class MCPServerManifest:
    id: str
    name: str
    description: str
    command: str | None
    url: str | None
    enabled: bool
    trust_level: str
    scopes: list[str]
    auth_ref: str | None
    status: str
    metadata: dict
    created_at: str
    updated_at: str

    def as_api(self) -> dict:
        return redact(self.__dict__)


class MCPServersRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def list(self) -> list[MCPServerManifest]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM mcp_servers ORDER BY updated_at DESC, name ASC").fetchall()
        return [_from_row(row) for row in rows]

    def get(self, server_id: str) -> MCPServerManifest | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        return _from_row(row) if row else None

    def add(
        self,
        *,
        name: str,
        url: str | None = None,
        command: str | None = None,
        description: str = "",
        trust_level: str = "untrusted",
        scopes: list[str] | None = None,
        auth_ref: str | None = None,
        metadata: dict | None = None,
    ) -> MCPServerManifest:
        name = name.strip()
        if not name:
            raise ValueError("Nom MCP requis.")
        if not (url or command):
            raise ValueError("Un MCP server doit declarer une url ou une commande.")
        trust_level = _trust_level(trust_level)
        enabled = trust_level in {"builtin", "local"} and not (trust_level == "untrusted" and self.config.capabilities_untrusted_disabled_by_default)
        server_id = _safe_id(name) or uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO mcp_servers(
                    id, name, description, command, url, enabled, trust_level, scopes_json,
                    auth_ref, status, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manifest_only', ?, ?, ?)
                """,
                (
                    server_id,
                    name,
                    description,
                    command,
                    url,
                    1 if enabled else 0,
                    trust_level,
                    json.dumps(scopes or ["external"], ensure_ascii=False),
                    auth_ref,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                    now,
                    now,
                ),
            )
        server = self.get(server_id)
        self.events.add("mcp.server.added", server.as_api() if server else {"id": server_id})
        return server

    def patch(self, server_id: str, values: dict) -> MCPServerManifest | None:
        current = self.get(server_id)
        if current is None:
            return None
        allowed = {"name", "description", "command", "url", "enabled", "trust_level", "scopes", "auth_ref", "status", "metadata"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Champs MCP non modifiables: {', '.join(sorted(unknown))}")
        next_values = {
            "name": str(values.get("name", current.name)).strip() or current.name,
            "description": str(values.get("description", current.description)),
            "command": values.get("command", current.command),
            "url": values.get("url", current.url),
            "enabled": bool(values.get("enabled", current.enabled)),
            "trust_level": _trust_level(str(values.get("trust_level", current.trust_level))),
            "scopes": list(values.get("scopes", current.scopes) or []),
            "auth_ref": values.get("auth_ref", current.auth_ref),
            "status": str(values.get("status", current.status)),
            "metadata": redact(values.get("metadata", current.metadata) or {}),
        }
        if next_values["trust_level"] == "blocked":
            next_values["enabled"] = False
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE mcp_servers
                SET name = ?, description = ?, command = ?, url = ?, enabled = ?,
                    trust_level = ?, scopes_json = ?, auth_ref = ?, status = ?,
                    metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_values["name"],
                    next_values["description"],
                    next_values["command"],
                    next_values["url"],
                    1 if next_values["enabled"] else 0,
                    next_values["trust_level"],
                    json.dumps(next_values["scopes"], ensure_ascii=False),
                    next_values["auth_ref"],
                    next_values["status"],
                    json.dumps(next_values["metadata"], ensure_ascii=False),
                    now,
                    server_id,
                ),
            )
        server = self.get(server_id)
        self.events.add("capability.updated", {"id": f"mcp_server:{server_id}", "type": "mcp_server"})
        return server

    def delete(self, server_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            cursor = conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
        return cursor.rowcount > 0


def _from_row(row) -> MCPServerManifest:
    return MCPServerManifest(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        command=row["command"],
        url=row["url"],
        enabled=bool(row["enabled"]),
        trust_level=row["trust_level"],
        scopes=json.loads(row["scopes_json"] or "[]"),
        auth_ref=row["auth_ref"],
        status=row["status"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _safe_id(name: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", name.strip().lower()).strip("-")
    return candidate[:128] if SAFE_ID.match(candidate) else ""


def _trust_level(value: str) -> str:
    lowered = value.strip().lower() or "untrusted"
    if lowered not in TRUST_LEVELS:
        raise ValueError("trust_level MCP invalide.")
    return lowered


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
