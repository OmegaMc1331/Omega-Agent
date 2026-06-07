from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action

VALID_DELEGATION_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}


@dataclass(frozen=True)
class Delegation:
    id: str
    session_id: str
    parent_agent_id: str
    child_agent_id: str
    task: str
    status: str
    result: str
    created_at: str
    updated_at: str
    metadata_json: str

    @property
    def metadata(self) -> dict:
        try:
            payload = json.loads(self.metadata_json)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}


class DelegationsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def create(
        self,
        session_id: str,
        parent_agent_id: str,
        child_agent_id: str,
        task: str,
        metadata: dict | None = None,
    ) -> Delegation:
        if not task.strip():
            raise ValueError("Tache de delegation vide.")
        now = utc_now()
        delegation = Delegation(
            uuid4().hex,
            session_id,
            parent_agent_id,
            child_agent_id,
            task.strip(),
            "queued",
            "",
            now,
            now,
            json.dumps(metadata or {}, ensure_ascii=False),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO delegations(
                    id, session_id, parent_agent_id, child_agent_id, task,
                    status, result, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delegation.id,
                    delegation.session_id,
                    delegation.parent_agent_id,
                    delegation.child_agent_id,
                    delegation.task,
                    delegation.status,
                    delegation.result,
                    delegation.created_at,
                    delegation.updated_at,
                    delegation.metadata_json,
                ),
            )
        log_action(self.config, "delegation_created", {"delegation_id": delegation.id, "child_agent_id": child_agent_id})
        return delegation

    def list(self, session_id: str | None = None) -> list[Delegation]:
        sql = """
            SELECT id, session_id, parent_agent_id, child_agent_id, task, status,
                   result, created_at, updated_at, metadata_json
            FROM delegations
        """
        params: list[object] = []
        if session_id:
            sql += " WHERE session_id = ?"
            params.append(session_id)
        sql += " ORDER BY updated_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, delegation_id: str) -> Delegation | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, session_id, parent_agent_id, child_agent_id, task, status,
                       result, created_at, updated_at, metadata_json
                FROM delegations
                WHERE id = ?
                """,
                (delegation_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def update_status(self, delegation_id: str, status: str, result: str | None = None, metadata: dict | None = None) -> Delegation | None:
        if status not in VALID_DELEGATION_STATUSES:
            raise ValueError("Status delegation invalide.")
        current = self.get(delegation_id)
        if current is None:
            return None
        next_metadata = current.metadata
        if metadata:
            next_metadata.update(metadata)
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE delegations SET status = ?, result = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (status, current.result if result is None else result, json.dumps(next_metadata, ensure_ascii=False), now, delegation_id),
            )
        log_action(self.config, "delegation_updated", {"delegation_id": delegation_id, "status": status})
        return self.get(delegation_id)

    def cancel(self, delegation_id: str) -> Delegation | None:
        current = self.get(delegation_id)
        if current is None:
            return None
        if current.status in {"completed", "failed", "cancelled"}:
            return current
        return self.update_status(delegation_id, "cancelled")

    def depth_for_session(self, session_id: str) -> int:
        running = [item for item in self.list(session_id=session_id) if item.status in {"queued", "running"}]
        depths = [int(item.metadata.get("depth") or 0) for item in running]
        return max(depths or [0])

    def _from_row(self, row) -> Delegation:
        return Delegation(
            row["id"],
            row["session_id"],
            row["parent_agent_id"],
            row["child_agent_id"],
            row["task"],
            row["status"],
            row["result"],
            row["created_at"],
            row["updated_at"],
            row["metadata_json"],
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
