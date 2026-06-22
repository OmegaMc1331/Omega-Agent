from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.connectors.base import ConnectorUsageEvent
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class ConnectorUsageStore:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def record(
        self,
        connector_id: str,
        operation_id: str | None,
        *,
        status: str,
        latency_ms: int | None = None,
        error: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> ConnectorUsageEvent:
        now = datetime.now(timezone.utc).isoformat()
        event = ConnectorUsageEvent(
            id=uuid4().hex,
            connector_id=connector_id,
            operation_id=operation_id,
            run_id=run_id,
            session_id=session_id,
            status=status,
            latency_ms=latency_ms,
            error=error,
            created_at=now,
            metadata=redact(metadata or {}),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO connector_usage_events(
                    id, connector_id, operation_id, run_id, session_id, status,
                    latency_ms, error, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.connector_id,
                    event.operation_id,
                    event.run_id,
                    event.session_id,
                    event.status,
                    event.latency_ms,
                    redact(event.error),
                    event.created_at,
                    json.dumps(event.metadata, ensure_ascii=False),
                ),
            )
        return event

    def list(self, connector_id: str | None = None, limit: int = 100) -> list[ConnectorUsageEvent]:
        query = "SELECT * FROM connector_usage_events"
        params: list[object] = []
        if connector_id:
            query += " WHERE connector_id = ?"
            params.append(connector_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [
            ConnectorUsageEvent(
                id=row["id"],
                connector_id=row["connector_id"],
                operation_id=row["operation_id"],
                run_id=row["run_id"],
                session_id=row["session_id"],
                status=row["status"],
                latency_ms=row["latency_ms"],
                error=row["error"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        ]
