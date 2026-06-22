from __future__ import annotations

import json
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.events.event_redaction import event_for_ui
from omega_agent.events.protocol import EVENT_VERSION, OmegaEvent, event_type_catalog
from omega_agent.runtime.storage import connect_runtime_db


class EventStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.init_db()

    def init_db(self) -> None:
        with connect_runtime_db(self.config):
            pass

    def persist(self, event: OmegaEvent) -> OmegaEvent:
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events_v2(
                    id, version, type, timestamp, session_id, run_id, step_id, user_id,
                    source, level, visibility, payload_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.version,
                    event.type,
                    event.timestamp,
                    event.session_id,
                    event.run_id,
                    event.step_id,
                    event.user_id,
                    event.source,
                    event.level,
                    event.visibility,
                    json.dumps(event.payload, ensure_ascii=False),
                    json.dumps(event.metadata, ensure_ascii=False),
                ),
            )
        return event

    def get(self, event_id: str, *, for_ui: bool = True) -> OmegaEvent | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, version, type, timestamp, session_id, run_id, step_id, user_id,
                       source, level, visibility, payload_json, metadata_json
                FROM events_v2 WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        event = _row_to_event(row)
        if not for_ui:
            return event
        return event_for_ui(event, max_chars=_max_trace_chars(self.config))

    def list(
        self,
        *,
        limit: int = 100,
        type: str | None = None,
        source: str | None = None,
        level: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        for_ui: bool = True,
    ) -> list[OmegaEvent]:
        query = """
            SELECT id, version, type, timestamp, session_id, run_id, step_id, user_id,
                   source, level, visibility, payload_json, metadata_json
            FROM events_v2
        """
        clauses: list[str] = []
        params: list[Any] = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if for_ui:
            clauses.append("visibility != 'internal'")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        events = [_row_to_event(row) for row in rows]
        if not for_ui:
            return events
        return [event for event in (event_for_ui(item, max_chars=_max_trace_chars(self.config)) for item in events) if event is not None]

    def replay(
        self,
        *,
        since_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
        for_ui: bool = True,
    ) -> list[OmegaEvent]:
        replay_limit = limit if limit is not None else getattr(self.config, "events_max_replay_events", 500)
        replay_limit = max(1, min(int(replay_limit), getattr(self.config, "events_max_replay_events", 500)))
        clauses: list[str] = []
        params: list[Any] = []
        if since_id:
            since_event = self.get(since_id, for_ui=False)
            if since_event is not None:
                clauses.append("timestamp > ?")
                params.append(since_event.timestamp)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if for_ui:
            clauses.append("visibility != 'internal'")
        query = """
            SELECT id, version, type, timestamp, session_id, run_id, step_id, user_id,
                   source, level, visibility, payload_json, metadata_json
            FROM events_v2
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(replay_limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        events = [_row_to_event(row) for row in rows]
        if not for_ui:
            return events
        return [event for event in (event_for_ui(item, max_chars=_max_trace_chars(self.config)) for item in events) if event is not None]

    def types(self) -> list[str]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT DISTINCT type FROM events_v2 ORDER BY type").fetchall()
        return sorted(set(event_type_catalog()) | {row["type"] for row in rows})


def _row_to_event(row) -> OmegaEvent:
    return OmegaEvent(
        id=row["id"],
        version=row["version"] or EVENT_VERSION,
        type=row["type"],
        timestamp=row["timestamp"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        step_id=row["step_id"],
        user_id=row["user_id"],
        source=row["source"],
        level=row["level"],
        visibility=row["visibility"],
        payload=_loads(row["payload_json"]),
        metadata=_loads(row["metadata_json"]),
    )


def _loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _max_trace_chars(config: OmegaConfig) -> int:
    return max(1000, int(getattr(config, "evals_max_trace_chars", 20000)))
