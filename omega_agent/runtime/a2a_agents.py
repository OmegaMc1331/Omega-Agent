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
class A2AAgentManifest:
    id: str
    name: str
    description: str
    endpoint: str | None
    agent_card: dict
    enabled: bool
    trust_level: str
    scopes: list[str]
    status: str
    metadata: dict
    created_at: str
    updated_at: str

    def as_api(self) -> dict:
        return redact(self.__dict__)


class A2AAgentsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def list(self) -> list[A2AAgentManifest]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM a2a_agents ORDER BY updated_at DESC, name ASC").fetchall()
        return [_from_row(row) for row in rows]

    def get(self, agent_id: str) -> A2AAgentManifest | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM a2a_agents WHERE id = ?", (agent_id,)).fetchone()
        return _from_row(row) if row else None

    def add(
        self,
        *,
        name: str,
        endpoint: str | None = None,
        description: str = "",
        agent_card: dict | None = None,
        trust_level: str = "untrusted",
        scopes: list[str] | None = None,
        metadata: dict | None = None,
    ) -> A2AAgentManifest:
        name = name.strip()
        if not name:
            raise ValueError("Nom A2A requis.")
        trust_level = _trust_level(trust_level)
        enabled = trust_level in {"builtin", "local"} and not (trust_level == "untrusted" and self.config.capabilities_untrusted_disabled_by_default)
        agent_id = _safe_id(name) or uuid4().hex
        now = _now()
        card = redact(agent_card or {"name": name, "description": description, "endpoint": endpoint})
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO a2a_agents(
                    id, name, description, endpoint, agent_card_json, enabled,
                    trust_level, scopes_json, status, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manifest_only', ?, ?, ?)
                """,
                (
                    agent_id,
                    name,
                    description,
                    endpoint,
                    json.dumps(card, ensure_ascii=False),
                    1 if enabled else 0,
                    trust_level,
                    json.dumps(scopes or ["external"], ensure_ascii=False),
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                    now,
                    now,
                ),
            )
        agent = self.get(agent_id)
        self.events.add("a2a.agent.added", agent.as_api() if agent else {"id": agent_id})
        return agent

    def patch(self, agent_id: str, values: dict) -> A2AAgentManifest | None:
        current = self.get(agent_id)
        if current is None:
            return None
        allowed = {"name", "description", "endpoint", "agent_card", "enabled", "trust_level", "scopes", "status", "metadata"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Champs A2A non modifiables: {', '.join(sorted(unknown))}")
        next_values = {
            "name": str(values.get("name", current.name)).strip() or current.name,
            "description": str(values.get("description", current.description)),
            "endpoint": values.get("endpoint", current.endpoint),
            "agent_card": redact(values.get("agent_card", current.agent_card) or {}),
            "enabled": bool(values.get("enabled", current.enabled)),
            "trust_level": _trust_level(str(values.get("trust_level", current.trust_level))),
            "scopes": list(values.get("scopes", current.scopes) or []),
            "status": str(values.get("status", current.status)),
            "metadata": redact(values.get("metadata", current.metadata) or {}),
        }
        if next_values["trust_level"] == "blocked":
            next_values["enabled"] = False
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE a2a_agents
                SET name = ?, description = ?, endpoint = ?, agent_card_json = ?,
                    enabled = ?, trust_level = ?, scopes_json = ?, status = ?,
                    metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_values["name"],
                    next_values["description"],
                    next_values["endpoint"],
                    json.dumps(next_values["agent_card"], ensure_ascii=False),
                    1 if next_values["enabled"] else 0,
                    next_values["trust_level"],
                    json.dumps(next_values["scopes"], ensure_ascii=False),
                    next_values["status"],
                    json.dumps(next_values["metadata"], ensure_ascii=False),
                    now,
                    agent_id,
                ),
            )
        agent = self.get(agent_id)
        self.events.add("capability.updated", {"id": f"a2a_agent:{agent_id}", "type": "a2a_agent"})
        return agent

    def delete(self, agent_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            cursor = conn.execute("DELETE FROM a2a_agents WHERE id = ?", (agent_id,))
        return cursor.rowcount > 0


def _from_row(row) -> A2AAgentManifest:
    return A2AAgentManifest(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        endpoint=row["endpoint"],
        agent_card=json.loads(row["agent_card_json"] or "{}"),
        enabled=bool(row["enabled"]),
        trust_level=row["trust_level"],
        scopes=json.loads(row["scopes_json"] or "[]"),
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
        raise ValueError("trust_level A2A invalide.")
    return lowered


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
