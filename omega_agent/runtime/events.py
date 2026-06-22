from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.events.event_bus import EventBus
from omega_agent.events.protocol import infer_level, infer_source
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action
from omega_agent.security.redaction import redact

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
        redacted_payload = redact(payload)
        event = RuntimeEvent(
            id=uuid4().hex,
            type=event_type,
            payload=redacted_payload,
            created_at=datetime.now(timezone.utc).isoformat(),
            session_id=session_id or redacted_payload.get("session_id"),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO events(id, type, session_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event.id, event.type, event.session_id, json.dumps(event.payload, ensure_ascii=False), event.created_at),
            )
        if getattr(self.config, "events_enabled", True):
            try:
                EventBus(self.config).emit(
                    event_type,
                    redacted_payload,
                    session_id=event.session_id,
                    run_id=_optional_str(redacted_payload.get("run_id")),
                    step_id=_optional_str(redacted_payload.get("step_id")),
                    source=infer_source(event_type),
                    level=infer_level(event_type),
                    visibility=_visibility_for_event(event_type),
                    metadata={"legacy_event_id": event.id},
                )
            except Exception:
                pass
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


def _visibility_for_event(event_type: str) -> str:
    if event_type in REASONING_EVENT_TYPES and event_type.endswith((".analysis", ".plan")):
        return "redacted"
    if event_type.endswith(".internal"):
        return "internal"
    return "public"


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
