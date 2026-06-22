from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


@dataclass(frozen=True)
class CapabilityUsageEvent:
    id: str
    capability_id: str
    run_id: str | None
    session_id: str | None
    status: str
    latency_ms: int | None
    error: str | None
    created_at: str
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


class CapabilityUsageStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def record(
        self,
        capability_id: str,
        status: str,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
        metadata: dict | None = None,
    ) -> CapabilityUsageEvent | None:
        if not self.config.capabilities_usage_logging:
            return None
        event = CapabilityUsageEvent(
            id=uuid4().hex,
            capability_id=capability_id,
            run_id=run_id,
            session_id=session_id,
            status=status,
            latency_ms=latency_ms,
            error=redact(str(error)) if error else None,
            created_at=_now(),
            metadata=redact(metadata or {}),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO capability_usage_events(
                    id, capability_id, run_id, session_id, status, latency_ms,
                    error, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.capability_id,
                    event.run_id,
                    event.session_id,
                    event.status,
                    event.latency_ms,
                    event.error,
                    event.created_at,
                    json.dumps(event.metadata, ensure_ascii=False),
                ),
            )
        event_type = "capability.error" if status in {"failed", "denied", "error"} else "capability.used"
        self.events.add(event_type, event.as_api(), session_id=session_id)
        return event

    def list(self, limit: int = 100, capability_id: str | None = None) -> list[CapabilityUsageEvent]:
        query = "SELECT * FROM capability_usage_events"
        params: list[object] = []
        if capability_id:
            query += " WHERE capability_id = ?"
            params.append(capability_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_from_row(row) for row in rows]


def _from_row(row) -> CapabilityUsageEvent:
    return CapabilityUsageEvent(
        id=row["id"],
        capability_id=row["capability_id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        status=row["status"],
        latency_ms=row["latency_ms"],
        error=row["error"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
