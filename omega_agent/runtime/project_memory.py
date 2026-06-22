from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.memory_provenance import ProvenanceInput, default_manual_provenance, normalize_provenance
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action
from omega_agent.security.pii import contains_sensitive, redact_memory_text
from omega_agent.security.redaction import redact

MEMORY_SCOPES = {"global", "project", "session", "agent", "run"}
MEMORY_TYPES = {"fact", "preference", "decision", "procedure", "warning", "entity", "project_note", "tool_observation"}
MEMORY_STATUSES = {"active", "archived", "deleted"}
CREATED_BY = {"user", "omega", "tool", "import"}
SUGGESTION_STATUSES = {"pending", "accepted", "rejected"}


@dataclass(frozen=True)
class ProjectMemory:
    id: str
    scope: str
    scope_id: str | None
    project_id: str | None
    session_id: str | None
    run_id: str | None
    key: str
    content: str
    summary: str | None
    type: str
    confidence: float
    importance: int
    status: str
    tags: list[str]
    tags_json: str
    provenance: dict
    provenance_json: str
    created_by: str
    created_at: str
    updated_at: str
    expires_at: str | None
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class MemoryProvenanceRecord:
    id: str
    memory_id: str
    source_type: str
    source_id: str | None
    source_label: str | None
    quote: str | None
    created_at: str
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class MemoryConflict:
    id: str
    memory_a_id: str
    memory_b_id: str
    conflict_type: str
    status: str
    resolution: str | None
    created_at: str
    resolved_at: str | None
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class MemorySuggestion:
    id: str
    run_id: str
    project_id: str | None
    suggested_type: str
    content: str
    reason: str
    status: str
    created_at: str
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


class ProjectMemoryStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def create_memory(
        self,
        scope: str,
        content: str,
        type: str,
        provenance: Any,
        tags: list[str] | None = None,
        confidence: float = 0.8,
        *,
        key: str = "",
        project_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        scope_id: str | None = None,
        importance: int = 3,
        created_by: str = "user",
        summary: str | None = None,
        metadata: dict | None = None,
    ) -> ProjectMemory:
        if not self.config.memory_enabled or not self.config.memory_project_memory_enabled:
            raise ValueError("Memoire projet desactivee.")
        if scope not in MEMORY_SCOPES:
            raise ValueError("Scope memoire invalide.")
        if type not in MEMORY_TYPES:
            raise ValueError("Type de memoire invalide.")
        if created_by not in CREATED_BY:
            raise ValueError("Createur de memoire invalide.")
        clean_content = _clean_text(content)
        if not clean_content:
            raise ValueError("Memoire vide.")
        provenances = normalize_provenance(provenance)
        if self.config.memory_require_provenance and not provenances:
            raise ValueError("Provenance requise pour creer une memoire.")
        redacted_content = self._redact_and_validate(clean_content)
        redacted_summary = self._redact_and_validate(summary) if summary else None
        redacted_key = self._redact_and_validate(key.strip() or _derive_key(redacted_content))
        now = _now()
        ttl_days = self.config.memory_default_ttl_days
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat() if ttl_days else None
        tags_json = _json_list(tags or [])
        provenance_json = json.dumps([item.as_json() for item in provenances], ensure_ascii=False)
        metadata_json = json.dumps(redact(metadata or {}), ensure_ascii=False)
        memory = ProjectMemory(
            id=uuid4().hex,
            scope=scope,
            scope_id=scope_id,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            key=redacted_key,
            content=redacted_content,
            summary=redacted_summary,
            type=type,
            confidence=max(0.0, min(1.0, float(confidence))),
            importance=max(0, min(5, int(importance))),
            status="active",
            tags=tags or [],
            tags_json=tags_json,
            provenance=json.loads(provenance_json),
            provenance_json=provenance_json,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            metadata=json.loads(metadata_json),
            metadata_json=metadata_json,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO memory_entries(
                    id, scope, scope_id, project_id, session_id, run_id, key, content, summary, type,
                    confidence, importance, status, tags_json, provenance_json, created_by,
                    created_at, updated_at, expires_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    memory.scope,
                    memory.scope_id,
                    memory.project_id,
                    memory.session_id,
                    memory.run_id,
                    memory.key,
                    memory.content,
                    memory.summary,
                    memory.type,
                    memory.confidence,
                    memory.importance,
                    memory.status,
                    memory.tags_json,
                    memory.provenance_json,
                    memory.created_by,
                    memory.created_at,
                    memory.updated_at,
                    memory.expires_at,
                    memory.metadata_json,
                ),
            )
            for item in provenances:
                self._insert_provenance(conn, memory.id, item)
        conflicts = self.detect_memory_conflicts(memory)
        self.events.add("memory.created", {"memory_id": memory.id, "scope": scope, "type": type, "conflicts": len(conflicts)}, session_id=session_id)
        log_action(self.config, "memory_created", {"memory_id": memory.id, "scope": scope, "type": type})
        return memory

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        *,
        confidence: float | None = None,
        importance: int | None = None,
        summary: str | None = None,
        key: str | None = None,
    ) -> ProjectMemory | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
        updates: dict[str, object] = {"updated_at": _now()}
        if content is not None:
            clean_content = _clean_text(content)
            if not clean_content:
                raise ValueError("Memoire vide.")
            updates["content"] = self._redact_and_validate(clean_content)
        if tags is not None:
            updates["tags_json"] = _json_list(tags)
        if status is not None:
            if status not in MEMORY_STATUSES:
                raise ValueError("Statut de memoire invalide.")
            updates["status"] = status
        if confidence is not None:
            updates["confidence"] = max(0.0, min(1.0, float(confidence)))
        if importance is not None:
            updates["importance"] = max(0, min(5, int(importance)))
        if summary is not None:
            updates["summary"] = self._redact_and_validate(summary) if summary else None
        if key is not None:
            clean_key = key.strip()
            if clean_key:
                updates["key"] = self._redact_and_validate(clean_key)
        assignments = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [memory_id]
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE memory_entries SET {assignments} WHERE id = ?", tuple(params))
        event_type = "memory.deleted" if status == "deleted" else "memory.archived" if status == "archived" else "memory.updated"
        self.events.add(event_type, {"memory_id": memory_id}, session_id=current.session_id)
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        return self.update_memory(memory_id, status="deleted") is not None

    def archive_memory(self, memory_id: str) -> bool:
        return self.update_memory(memory_id, status="archived") is not None

    def search_memory(self, query: str, scope: str | None = None, project_id: str | None = None, limit: int = 10) -> list[ProjectMemory]:
        clauses = ["status = 'active'"]
        params: list[object] = []
        needle = query.strip()
        if needle:
            like = f"%{needle}%"
            clauses.append("(key LIKE ? OR content LIKE ? OR summary LIKE ? OR tags_json LIKE ?)")
            params.extend([like, like, like, like])
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if project_id:
            clauses.append("(project_id = ? OR scope = 'global')")
            params.append(project_id)
        params.append(max(1, int(limit)))
        sql = f"SELECT * FROM memory_entries WHERE {' AND '.join(clauses)} ORDER BY importance DESC, updated_at DESC LIMIT ?"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def get_relevant_memories(self, message: str, project_id: str | None, session_id: str | None, limit: int = 8) -> list[ProjectMemory]:
        max_limit = max(1, min(int(limit), self.config.memory_max_context_memories))
        terms = {part.lower() for part in message.replace("\n", " ").split() if len(part) >= 3}
        clauses = ["status = 'active'"]
        params: list[object] = []
        if project_id:
            clauses.append("(project_id = ? OR project_id IS NULL OR scope = 'global')")
            params.append(project_id)
        if session_id:
            clauses.append("(session_id = ? OR session_id IS NULL)")
            params.append(session_id)
        sql = f"SELECT * FROM memory_entries WHERE {' AND '.join(clauses)} ORDER BY importance DESC, updated_at DESC LIMIT 200"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        memories = [self._from_row(row) for row in rows]
        scored = sorted(memories, key=lambda item: _score_memory(item, terms), reverse=True)
        return scored[:max_limit]

    def list_memories(self, scope: str | None = None, project_id: str | None = None, status: str = "active", limit: int = 100) -> list[ProjectMemory]:
        if status not in MEMORY_STATUSES:
            raise ValueError("Statut de memoire invalide.")
        clauses = ["status = ?"]
        params: list[object] = [status]
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        params.append(max(1, int(limit)))
        sql = f"SELECT * FROM memory_entries WHERE {' AND '.join(clauses)} ORDER BY importance DESC, updated_at DESC LIMIT ?"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> ProjectMemory | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM memory_entries WHERE id = ?", (memory_id,)).fetchone()
        return self._from_row(row) if row else None

    def create_provenance(
        self,
        memory_id: str,
        source_type: str,
        source_id: str | None = None,
        quote: str | None = None,
        *,
        source_label: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryProvenanceRecord:
        item = normalize_provenance(
            {
                "source_type": source_type,
                "source_id": source_id,
                "source_label": source_label,
                "quote": quote,
                "metadata": metadata or {},
            }
        )[0]
        with connect_runtime_db(self.config) as conn:
            record = self._insert_provenance(conn, memory_id, item)
        self.events.add("memory.provenance.created", {"memory_id": memory_id, "provenance_id": record.id})
        return record

    def list_provenance(self, memory_id: str) -> list[MemoryProvenanceRecord]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM memory_provenance WHERE memory_id = ? ORDER BY created_at", (memory_id,)).fetchall()
        return [self._provenance_from_row(row) for row in rows]

    def detect_memory_conflicts(self, memory: ProjectMemory) -> list[MemoryConflict]:
        if not memory.key:
            return []
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE id != ? AND status = 'active' AND key = ? AND COALESCE(project_id, '') = COALESCE(?, '')
                """,
                (memory.id, memory.key, memory.project_id),
            ).fetchall()
            created: list[MemoryConflict] = []
            for row in rows:
                other = self._from_row(row)
                if other.content == memory.content:
                    continue
                existing = conn.execute(
                    """
                    SELECT * FROM memory_conflicts
                    WHERE status = 'open'
                      AND ((memory_a_id = ? AND memory_b_id = ?) OR (memory_a_id = ? AND memory_b_id = ?))
                    """,
                    (memory.id, other.id, other.id, memory.id),
                ).fetchone()
                if existing:
                    created.append(self._conflict_from_row(existing))
                    continue
                now = _now()
                conflict_id = uuid4().hex
                metadata_json = json.dumps({"key": memory.key}, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO memory_conflicts(id, memory_a_id, memory_b_id, conflict_type, status, resolution, created_at, resolved_at, metadata_json)
                    VALUES (?, ?, ?, ?, 'open', NULL, ?, NULL, ?)
                    """,
                    (conflict_id, other.id, memory.id, "same_key_different_content", now, metadata_json),
                )
                created.append(
                    MemoryConflict(conflict_id, other.id, memory.id, "same_key_different_content", "open", None, now, None, {"key": memory.key}, metadata_json)
                )
        if created:
            self.events.add("memory.conflict.detected", {"memory_id": memory.id, "count": len(created)}, session_id=memory.session_id)
        return created

    def list_conflicts(self, project_id: str | None = None, status: str = "open") -> list[MemoryConflict]:
        clauses = ["c.status = ?"]
        params: list[object] = [status]
        if project_id:
            clauses.append("(a.project_id = ? OR b.project_id = ?)")
            params.extend([project_id, project_id])
        sql = f"""
            SELECT c.*
            FROM memory_conflicts c
            JOIN memory_entries a ON a.id = c.memory_a_id
            JOIN memory_entries b ON b.id = c.memory_b_id
            WHERE {' AND '.join(clauses)}
            ORDER BY c.created_at DESC
        """
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._conflict_from_row(row) for row in rows]

    def compact_project_memory(self, project_id: str) -> dict:
        if not self.config.memory_compaction_enabled:
            return {"project_id": project_id, "enabled": False, "archived": 0, "summary": "Compaction desactivee."}
        memories = self.list_memories(project_id=project_id, status="active", limit=500)
        seen: dict[tuple[str, str], ProjectMemory] = {}
        archived = 0
        for memory in memories:
            key = (memory.type, memory.key.lower())
            if key not in seen:
                seen[key] = memory
                continue
            if memory.importance <= seen[key].importance and memory.confidence <= seen[key].confidence:
                self.archive_memory(memory.id)
                archived += 1
        result = {"project_id": project_id, "enabled": True, "active": len(memories) - archived, "archived": archived}
        self.events.add("memory.compacted", result)
        return result

    def create_suggestion(
        self,
        run_id: str,
        suggested_type: str,
        content: str,
        reason: str,
        *,
        project_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemorySuggestion:
        if suggested_type not in MEMORY_TYPES:
            raise ValueError("Type de suggestion memoire invalide.")
        redacted_content = self._redact_and_validate(content)
        now = _now()
        metadata_json = json.dumps(redact(metadata or {}), ensure_ascii=False)
        suggestion = MemorySuggestion(uuid4().hex, run_id, project_id, suggested_type, redacted_content, self._redact_and_validate(reason), "pending", now, json.loads(metadata_json), metadata_json)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO memory_suggestions(id, run_id, project_id, suggested_type, content, reason, status, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.id,
                    suggestion.run_id,
                    suggestion.project_id,
                    suggestion.suggested_type,
                    suggestion.content,
                    suggestion.reason,
                    suggestion.status,
                    suggestion.created_at,
                    suggestion.metadata_json,
                ),
            )
        self.events.add("memory.suggestion.created", {"suggestion_id": suggestion.id, "run_id": run_id})
        return suggestion

    def list_suggestions(self, status: str = "pending", project_id: str | None = None, limit: int = 100) -> list[MemorySuggestion]:
        if status not in SUGGESTION_STATUSES:
            raise ValueError("Statut de suggestion invalide.")
        clauses = ["status = ?"]
        params: list[object] = [status]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        params.append(max(1, int(limit)))
        sql = f"SELECT * FROM memory_suggestions WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._suggestion_from_row(row) for row in rows]

    def accept_suggestion(self, suggestion_id: str, *, created_by: str = "user") -> ProjectMemory | None:
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion is None or suggestion.status != "pending":
            return None
        memory = self.create_memory(
            scope="project" if suggestion.project_id else "run",
            project_id=suggestion.project_id,
            run_id=suggestion.run_id,
            scope_id=suggestion.project_id or suggestion.run_id,
            content=suggestion.content,
            type=suggestion.suggested_type,
            provenance={"source_type": "run", "source_id": suggestion.run_id, "source_label": "Memory suggestion"},
            tags=["suggestion"],
            confidence=0.7,
            created_by=created_by,
            metadata={"accepted_suggestion_id": suggestion.id},
        )
        self._set_suggestion_status(suggestion_id, "accepted")
        self.events.add("memory.suggestion.accepted", {"suggestion_id": suggestion_id, "memory_id": memory.id})
        return memory

    def reject_suggestion(self, suggestion_id: str) -> bool:
        updated = self._set_suggestion_status(suggestion_id, "rejected")
        if updated:
            self.events.add("memory.suggestion.rejected", {"suggestion_id": suggestion_id})
        return updated

    def get_suggestion(self, suggestion_id: str) -> MemorySuggestion | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM memory_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return self._suggestion_from_row(row) if row else None

    def _set_suggestion_status(self, suggestion_id: str, status: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("UPDATE memory_suggestions SET status = ? WHERE id = ?", (status, suggestion_id))
        return result.rowcount > 0

    def _redact_and_validate(self, value: str | None) -> str:
        text = _clean_text(value or "")
        if self.config.memory_redaction_enabled:
            text = redact_memory_text(text)
        if contains_sensitive(text):
            raise ValueError("Contenu memoire refuse: secret ou donnee sensible detectee.")
        return text

    def _insert_provenance(self, conn, memory_id: str, item: ProvenanceInput) -> MemoryProvenanceRecord:
        now = _now()
        quote = self._redact_and_validate(item.quote) if item.quote else None
        source_label = self._redact_and_validate(item.source_label) if item.source_label else None
        metadata_json = json.dumps(redact(item.metadata or {}), ensure_ascii=False)
        record = MemoryProvenanceRecord(uuid4().hex, memory_id, item.source_type, item.source_id, source_label, quote, now, json.loads(metadata_json), metadata_json)
        conn.execute(
            """
            INSERT INTO memory_provenance(id, memory_id, source_type, source_id, source_label, quote, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record.id, record.memory_id, record.source_type, record.source_id, record.source_label, record.quote, record.created_at, record.metadata_json),
        )
        return record

    def _from_row(self, row) -> ProjectMemory:
        tags_json = row["tags_json"] or "[]"
        provenance_json = row["provenance_json"] or "{}"
        metadata_json = row["metadata_json"] or "{}"
        return ProjectMemory(
            id=row["id"],
            scope=row["scope"],
            scope_id=row["scope_id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            key=row["key"],
            content=row["content"],
            summary=row["summary"],
            type=row["type"],
            confidence=float(row["confidence"]),
            importance=int(row["importance"]),
            status=row["status"],
            tags=_json_load_list(tags_json),
            tags_json=tags_json,
            provenance=_json_load(provenance_json, []),
            provenance_json=provenance_json,
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            metadata=_json_load(metadata_json, {}),
            metadata_json=metadata_json,
        )

    def _provenance_from_row(self, row) -> MemoryProvenanceRecord:
        metadata_json = row["metadata_json"] or "{}"
        return MemoryProvenanceRecord(
            id=row["id"],
            memory_id=row["memory_id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            source_label=row["source_label"],
            quote=row["quote"],
            created_at=row["created_at"],
            metadata=_json_load(metadata_json, {}),
            metadata_json=metadata_json,
        )

    def _conflict_from_row(self, row) -> MemoryConflict:
        metadata_json = row["metadata_json"] or "{}"
        return MemoryConflict(
            id=row["id"],
            memory_a_id=row["memory_a_id"],
            memory_b_id=row["memory_b_id"],
            conflict_type=row["conflict_type"],
            status=row["status"],
            resolution=row["resolution"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            metadata=_json_load(metadata_json, {}),
            metadata_json=metadata_json,
        )

    def _suggestion_from_row(self, row) -> MemorySuggestion:
        metadata_json = row["metadata_json"] or "{}"
        return MemorySuggestion(
            id=row["id"],
            run_id=row["run_id"],
            project_id=row["project_id"],
            suggested_type=row["suggested_type"],
            content=row["content"],
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"],
            metadata=_json_load(metadata_json, {}),
            metadata_json=metadata_json,
        )


def default_project_memory_provenance(label: str = "Omega Control") -> dict:
    return default_manual_provenance(label)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: str) -> str:
    return str(value or "").strip()


def _derive_key(content: str) -> str:
    compact = " ".join(content.split())
    return compact[:64] or "memory"


def _json_list(values: list[str]) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    return json.dumps(clean, ensure_ascii=False)


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_load_list(value: str) -> list[str]:
    parsed = _json_load(value, [])
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _score_memory(memory: ProjectMemory, terms: set[str]) -> tuple[int, float, str]:
    text = f"{memory.key} {memory.content} {' '.join(memory.tags)}".lower()
    matches = sum(1 for term in terms if term in text)
    return (matches, memory.importance, memory.updated_at)
