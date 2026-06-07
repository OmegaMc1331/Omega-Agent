from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action

REASONING_EVENT_TYPES = {
    "reasoning.started",
    "reasoning.analysis",
    "reasoning.plan",
    "reasoning.step",
    "reasoning.tool_considered",
    "reasoning.tool_requested",
    "reasoning.tool_started",
    "reasoning.tool_completed",
    "reasoning.observation",
    "reasoning.approval_required",
    "reasoning.approval_resolved",
    "reasoning.summary",
    "reasoning.completed",
    "reasoning.error",
}


@dataclass(frozen=True)
class RuntimeEvent:
    id: str
    type: str
    payload: dict
    created_at: str
    session_id: str | None = None


class EventsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.init_db()

    def init_db(self) -> None:
        with connect_runtime_db(self.config):
            pass

    def add(self, event_type: str, payload: dict, session_id: str | None = None) -> RuntimeEvent:
        event = RuntimeEvent(
            id=uuid4().hex,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id or payload.get("session_id"),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO events(id, type, session_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event.id, event.type, event.session_id, json.dumps(event.payload, ensure_ascii=False), event.created_at),
            )
        log_action(self.config, "event", {"type": event_type, "session_id": event.session_id})
        return event

    def list_recent(self, limit: int = 100, event_type: str | None = None, session_id: str | None = None) -> list[RuntimeEvent]:
        query = "SELECT id, type, session_id, payload_json, created_at FROM events"
        clauses: list[str] = []
        params: list[object] = []
        if event_type:
            clauses.append("type = ?")
            params.append(event_type)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            RuntimeEvent(
                id=row["id"],
                type=row["type"],
                session_id=row["session_id"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
