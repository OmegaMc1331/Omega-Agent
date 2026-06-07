from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import DEFAULT_AGENT_PROFILE_ID
from omega_agent.runtime.storage import connect_runtime_db


@dataclass(frozen=True)
class Session:
    id: str
    title: str
    created_at: str
    updated_at: str
    status: str = "active"
    active_agent: str = "Omega Agent"
    active_agent_profile_id: str | None = DEFAULT_AGENT_PROFILE_ID
    project_id: str | None = None
    metadata_json: str = "{}"


@dataclass(frozen=True)
class Message:
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata_json: str = "{}"


class SessionsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.init_db()

    def init_db(self) -> None:
        with connect_runtime_db(self.config):
            pass

    def create_session(self, title: str = "Nouvelle session") -> Session:
        now = utc_now()
        session = Session(id=uuid4().hex, title=title.strip() or "Nouvelle session", created_at=now, updated_at=now)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO sessions(id, title, created_at, updated_at, status, active_agent, active_agent_profile_id, project_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.title,
                    session.created_at,
                    session.updated_at,
                    session.status,
                    session.active_agent,
                    session.active_agent_profile_id,
                    session.project_id,
                    session.metadata_json,
                ),
            )
        return session

    def default_session_id(self) -> str:
        sessions = self.list_sessions()
        if sessions:
            return sessions[0].id
        return self.create_session().id

    def list_sessions(self) -> list[Session]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at, status, active_agent, active_agent_profile_id, project_id, metadata_json
                FROM sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> Session | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at, status, active_agent, active_agent_profile_id, project_id, metadata_json
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return self._session_from_row(row) if row else None

    def rename_session(self, session_id: str, title: str) -> Session | None:
        return self.update_session(session_id, title=title)

    def update_session(self, session_id: str, title: str | None = None, status: str | None = None, metadata: dict | None = None) -> Session | None:
        current = self.get_session(session_id)
        if current is None:
            return None
        now = utc_now()
        next_title = title.strip() if title and title.strip() else current.title
        next_status = status or current.status
        next_metadata = json.dumps(metadata, ensure_ascii=False) if metadata is not None else current.metadata_json
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, status = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (next_title, next_status, next_metadata, now, session_id),
            )
        return self.get_session(session_id)

    def set_project(self, session_id: str, project_id: str | None) -> Session | None:
        if self.get_session(session_id) is None:
            return None
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE sessions SET project_id = ?, updated_at = ? WHERE id = ?",
                (project_id, now, session_id),
            )
        return self.get_session(session_id)

    def set_agent_profile(self, session_id: str, profile_id: str) -> Session | None:
        if self.get_session(session_id) is None:
            return None
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE sessions SET active_agent_profile_id = ?, active_agent = ?, updated_at = ? WHERE id = ?",
                (profile_id, profile_id, now, session_id),
            )
        return self.get_session(session_id)

    def merge_metadata(self, session_id: str, values: dict) -> Session | None:
        current = self.get_session(session_id)
        if current is None:
            return None
        try:
            metadata = json.loads(current.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
        metadata.update(values)
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE sessions SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), now, session_id),
            )
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return result.rowcount > 0

    def add_message(self, session_id: str, role: str, content: str, metadata: dict | None = None) -> Message:
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("Role message invalide.")
        if self.get_session(session_id) is None:
            raise ValueError("Session introuvable.")
        now = utc_now()
        message = Message(uuid4().hex, session_id, role, content, now, json.dumps(metadata or {}, ensure_ascii=False))
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO messages(id, session_id, role, content, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message.id, message.session_id, message.role, message.content, message.created_at, message.metadata_json),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return message

    def list_messages(self, session_id: str) -> list[Message]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, created_at, metadata_json
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            Message(row["id"], row["session_id"], row["role"], row["content"], row["created_at"], row["metadata_json"])
            for row in rows
        ]

    def _session_from_row(self, row) -> Session:
        return Session(
            row["id"],
            row["title"],
            row["created_at"],
            row["updated_at"],
            row["status"],
            row["active_agent"],
            row["active_agent_profile_id"] or DEFAULT_AGENT_PROFILE_ID,
            row["project_id"],
            row["metadata_json"],
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
