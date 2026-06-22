from __future__ import annotations

import json
from dataclasses import dataclass

from omega_agent.config import OmegaConfig
from omega_agent.runtime.memory_provenance import default_manual_provenance
from omega_agent.runtime.project_memory import ProjectMemory, ProjectMemoryStore
from omega_agent.runtime.storage import connect_runtime_db


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
        self.project_memory = ProjectMemoryStore(config)
        with connect_runtime_db(config):
            pass

    def create(self, content: str, key: str = "", scope: str = "global", tags: list[str] | None = None) -> MemoryRecord:
        if scope not in {"global", "session", "project", "agent", "run"}:
            raise ValueError("Scope memoire invalide.")
        memory = self.project_memory.create_memory(
            scope=scope,
            content=content,
            tags=tags or [],
            key=key,
            type="fact",
            provenance=default_manual_provenance("Legacy MemoryStore"),
        )
        return self._from_project_memory(memory)

    def search(self, query: str = "", scope: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        records = [self._from_project_memory(memory) for memory in self.project_memory.search_memory(query=query, scope=scope, limit=limit)]
        if len(records) >= limit:
            return records[:limit]
        legacy = self._legacy_search(query=query, scope=scope, limit=limit - len(records))
        existing_ids = {record.id for record in records}
        records.extend(record for record in legacy if record.id not in existing_ids)
        return records[:limit]

    def delete(self, memory_id: str) -> bool:
        deleted = self.project_memory.delete_memory(memory_id)
        if deleted:
            return True
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
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

    def _from_project_memory(self, memory: ProjectMemory) -> MemoryRecord:
        return MemoryRecord(
            id=memory.id,
            scope=memory.scope,
            key=memory.key,
            content=memory.content,
            tags=memory.tags,
            tags_json=memory.tags_json,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )

    def _legacy_search(self, query: str = "", scope: str | None = None, limit: int = 50) -> list[MemoryRecord]:
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
