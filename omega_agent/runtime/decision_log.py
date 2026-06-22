from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.memory_provenance import default_manual_provenance, normalize_provenance
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.pii import contains_sensitive, redact_memory_text
from omega_agent.security.redaction import redact

DECISION_STATUSES = {"active", "superseded", "archived"}


@dataclass(frozen=True)
class Decision:
    id: str
    project_id: str | None
    session_id: str | None
    run_id: str | None
    title: str
    content: str
    reason: str
    alternatives: list[str]
    alternatives_json: str
    status: str
    created_by: str
    created_at: str
    updated_at: str
    provenance: dict
    provenance_json: str
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


class DecisionLog:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def add_decision(
        self,
        title: str,
        content: str,
        reason: str,
        project_id: str | None = None,
        run_id: str | None = None,
        provenance: Any = None,
        *,
        session_id: str | None = None,
        alternatives: list[str] | None = None,
        created_by: str = "user",
        metadata: dict | None = None,
    ) -> Decision:
        clean_title = self._redact_and_validate(title)
        clean_content = self._redact_and_validate(content)
        clean_reason = self._redact_and_validate(reason or "")
        if not clean_title or not clean_content:
            raise ValueError("Titre et contenu de decision requis.")
        provenances = normalize_provenance(provenance or default_manual_provenance("CLI"))
        if self.config.memory_require_provenance and not provenances:
            raise ValueError("Provenance requise pour une decision.")
        now = _now()
        alternatives_json = json.dumps([self._redact_and_validate(item) for item in (alternatives or [])], ensure_ascii=False)
        provenance_json = json.dumps([item.as_json() for item in provenances], ensure_ascii=False)
        metadata_json = json.dumps(redact(metadata or {}), ensure_ascii=False)
        decision = Decision(
            id=uuid4().hex,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            title=clean_title,
            content=clean_content,
            reason=clean_reason,
            alternatives=json.loads(alternatives_json),
            alternatives_json=alternatives_json,
            status="active",
            created_by=created_by,
            created_at=now,
            updated_at=now,
            provenance=json.loads(provenance_json),
            provenance_json=provenance_json,
            metadata=json.loads(metadata_json),
            metadata_json=metadata_json,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO decisions(
                    id, project_id, session_id, run_id, title, content, reason, alternatives_json,
                    status, created_by, created_at, updated_at, provenance_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.project_id,
                    decision.session_id,
                    decision.run_id,
                    decision.title,
                    decision.content,
                    decision.reason,
                    decision.alternatives_json,
                    decision.status,
                    decision.created_by,
                    decision.created_at,
                    decision.updated_at,
                    decision.provenance_json,
                    decision.metadata_json,
                ),
            )
        self.events.add("decision.created", {"decision_id": decision.id, "project_id": project_id}, session_id=session_id)
        return decision

    def list_decisions(self, project_id: str | None = None, status: str | None = None, limit: int = 100) -> list[Decision]:
        clauses: list[str] = []
        params: list[object] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            if status not in DECISION_STATUSES:
                raise ValueError("Statut de decision invalide.")
            clauses.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM decisions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def get_decision(self, decision_id: str) -> Decision | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        return self._from_row(row) if row else None

    def patch_decision(self, decision_id: str, values: dict) -> Decision | None:
        current = self.get_decision(decision_id)
        if current is None:
            return None
        allowed = {"title", "content", "reason", "status", "alternatives", "metadata"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Champs decision non modifiables: {', '.join(sorted(unknown))}")
        updates: dict[str, object] = {"updated_at": _now()}
        for key in ("title", "content", "reason"):
            if key in values and values[key] is not None:
                updates[key] = self._redact_and_validate(str(values[key]))
        if "status" in values and values["status"] is not None:
            status = str(values["status"])
            if status not in DECISION_STATUSES:
                raise ValueError("Statut de decision invalide.")
            updates["status"] = status
        if "alternatives" in values and values["alternatives"] is not None:
            alternatives = values["alternatives"] if isinstance(values["alternatives"], list) else []
            updates["alternatives_json"] = json.dumps([self._redact_and_validate(str(item)) for item in alternatives], ensure_ascii=False)
        if "metadata" in values and values["metadata"] is not None:
            updates["metadata_json"] = json.dumps(redact(values["metadata"] if isinstance(values["metadata"], dict) else {}), ensure_ascii=False)
        assignments = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [decision_id]
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE decisions SET {assignments} WHERE id = ?", tuple(params))
        self.events.add("decision.updated", {"decision_id": decision_id}, session_id=current.session_id)
        return self.get_decision(decision_id)

    def supersede_decision(self, decision_id: str, replacement_id: str) -> Decision | None:
        decision = self.patch_decision(decision_id, {"status": "superseded", "metadata": {"replacement_id": replacement_id}})
        if decision:
            self.events.add("decision.superseded", {"decision_id": decision_id, "replacement_id": replacement_id}, session_id=decision.session_id)
        return decision

    def archive_decision(self, decision_id: str) -> Decision | None:
        decision = self.patch_decision(decision_id, {"status": "archived"})
        if decision:
            self.events.add("decision.archived", {"decision_id": decision_id}, session_id=decision.session_id)
        return decision

    def _redact_and_validate(self, value: str) -> str:
        text = str(value or "").strip()
        if self.config.memory_redaction_enabled:
            text = redact_memory_text(text)
        if contains_sensitive(text):
            raise ValueError("Contenu decision refuse: secret ou donnee sensible detectee.")
        return text

    def _from_row(self, row) -> Decision:
        alternatives_json = row["alternatives_json"] or "[]"
        provenance_json = row["provenance_json"] or "{}"
        metadata_json = row["metadata_json"] or "{}"
        return Decision(
            id=row["id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            title=row["title"],
            content=row["content"],
            reason=row["reason"],
            alternatives=_json_list(alternatives_json),
            alternatives_json=alternatives_json,
            status=row["status"] or "active",
            created_by=row["created_by"] or "user",
            created_at=row["created_at"],
            updated_at=row["updated_at"] or row["created_at"],
            provenance=_json_load(provenance_json, []),
            provenance_json=provenance_json,
            metadata=_json_load(metadata_json, {}),
            metadata_json=metadata_json,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_list(value: str) -> list[str]:
    parsed = _json_load(value, [])
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]
