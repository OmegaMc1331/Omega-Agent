from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    scope: str
    key: str
    content: str
    tags: list[str]
    tags_json: str
    created_at: str
    updated_at: str


class MemoryStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def create(self, content: str, key: str = "", scope: str = "global", tags: list[str] | None = None) -> MemoryRecord:
        if scope not in {"global", "session", "project"}:
            raise ValueError("Scope memoire invalide.")
        now = datetime.now(timezone.utc).isoformat()
        record = MemoryRecord(
            id=uuid4().hex,
            scope=scope,
            key=key.strip() or content[:48],
            content=content,
            tags=tags or [],
            tags_json=json.dumps(tags or [], ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO memories(id, scope, key, content, tags_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (record.id, record.scope, record.key, record.content, record.tags_json, record.created_at, record.updated_at),
            )
        self.events.add("memory.created", {"memory_id": record.id, "scope": scope})
        log_action(self.config, "memory_created", {"memory_id": record.id, "scope": scope})
        return record

    def search(self, query: str = "", scope: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if query:
            clauses.append("(key LIKE ? OR content LIKE ? OR tags_json LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        sql = "SELECT id, scope, key, content, tags_json, created_at, updated_at FROM memories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, memory_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        if result.rowcount:
            log_action(self.config, "memory_deleted", {"memory_id": memory_id})
        return result.rowcount > 0

    def _from_row(self, row) -> MemoryRecord:
        tags_json = row["tags_json"]
        return MemoryRecord(
            id=row["id"],
            scope=row["scope"],
            key=row["key"],
            content=row["content"],
            tags=json.loads(tags_json),
            tags_json=tags_json,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
