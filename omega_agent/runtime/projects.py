from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.project_policy import ProjectPolicy, default_project_policy, validate_project_root

DEFAULT_PROJECT_ID = "default"


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    root_path: str
    description: str
    enabled: bool
    created_at: str
    updated_at: str
    policy_json: str
    metadata_json: str = "{}"

    @property
    def policy(self) -> ProjectPolicy:
        try:
            return ProjectPolicy.from_dict(json.loads(self.policy_json))
        except json.JSONDecodeError:
            return ProjectPolicy()

    @property
    def metadata(self) -> dict:
        try:
            return json.loads(self.metadata_json)
        except json.JSONDecodeError:
            return {}

    def as_api(self, linked_sessions: int = 0) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "root_path": self.root_path,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "policy": self.policy.to_dict(),
            "metadata": self.metadata,
            "policy_json": self.policy_json,
            "metadata_json": self.metadata_json,
            "linked_sessions": linked_sessions,
        }


@dataclass(frozen=True)
class ProjectPermission:
    id: str
    project_id: str
    permission: str
    value_json: str


class ProjectsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass
        self.ensure_default_project()

    def ensure_default_project(self) -> Project:
        now = utc_now()
        root_path = str(validate_project_root(self.config.workspace))
        policy_json = json.dumps(default_project_policy(self.config).to_dict(), ensure_ascii=False)
        current = self.get(DEFAULT_PROJECT_ID, include_disabled=True)
        with connect_runtime_db(self.config) as conn:
            if current is None:
                conn.execute(
                    """
                    INSERT INTO projects(id, name, root_path, description, enabled, created_at, updated_at, policy_json, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        DEFAULT_PROJECT_ID,
                        "Default Workspace",
                        root_path,
                        "Projet par defaut base sur OMEGA_WORKSPACE.",
                        1,
                        now,
                        now,
                        policy_json,
                        json.dumps({"default": True}, ensure_ascii=False),
                    ),
                )
                self._replace_permissions(conn, DEFAULT_PROJECT_ID, json.loads(policy_json))
            elif current.root_path != root_path:
                conn.execute(
                    "UPDATE projects SET root_path = ?, updated_at = ? WHERE id = ?",
                    (root_path, now, DEFAULT_PROJECT_ID),
                )
        return self.get(DEFAULT_PROJECT_ID, include_disabled=True)

    def create(
        self,
        name: str,
        root_path: str,
        description: str = "",
        enabled: bool = True,
        policy: dict | None = None,
        metadata: dict | None = None,
    ) -> Project:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Nom projet requis.")
        root = validate_project_root(root_path)
        project_policy = ProjectPolicy.from_dict(policy or default_project_policy(self.config).to_dict())
        now = utc_now()
        project = Project(
            id=uuid4().hex,
            name=clean_name,
            root_path=str(root),
            description=description.strip(),
            enabled=enabled,
            created_at=now,
            updated_at=now,
            policy_json=json.dumps(project_policy.to_dict(), ensure_ascii=False),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO projects(id, name, root_path, description, enabled, created_at, updated_at, policy_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.root_path,
                    project.description,
                    int(project.enabled),
                    project.created_at,
                    project.updated_at,
                    project.policy_json,
                    project.metadata_json,
                ),
            )
            self._replace_permissions(conn, project.id, project_policy.to_dict())
        return project

    def list(self, include_disabled: bool = True) -> list[Project]:
        sql = "SELECT id, name, root_path, description, enabled, created_at, updated_at, policy_json, metadata_json FROM projects"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY updated_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, project_id: str, include_disabled: bool = False) -> Project | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, name, root_path, description, enabled, created_at, updated_at, policy_json, metadata_json
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        project = self._from_row(row) if row else None
        if project is None:
            return None
        if not include_disabled and not project.enabled:
            return None
        return project

    def update(
        self,
        project_id: str,
        name: str | None = None,
        root_path: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        policy: dict | None = None,
        metadata: dict | None = None,
    ) -> Project | None:
        current = self.get(project_id, include_disabled=True)
        if current is None:
            return None
        clean_name = name.strip() if name is not None and name.strip() else current.name
        next_root = str(validate_project_root(root_path)) if root_path is not None else current.root_path
        next_description = description.strip() if description is not None else current.description
        next_enabled = current.enabled if enabled is None else enabled
        next_policy = ProjectPolicy.from_dict(policy) if policy is not None else current.policy
        next_metadata = metadata if metadata is not None else current.metadata
        now = utc_now()
        policy_json = json.dumps(next_policy.to_dict(), ensure_ascii=False)
        metadata_json = json.dumps(next_metadata, ensure_ascii=False)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE projects
                SET name = ?, root_path = ?, description = ?, enabled = ?, updated_at = ?, policy_json = ?, metadata_json = ?
                WHERE id = ?
                """,
                (clean_name, next_root, next_description, int(next_enabled), now, policy_json, metadata_json, project_id),
            )
            self._replace_permissions(conn, project_id, next_policy.to_dict())
        return self.get(project_id, include_disabled=True)

    def delete(self, project_id: str) -> bool:
        if project_id == DEFAULT_PROJECT_ID:
            raise ValueError("Le projet par defaut ne peut pas etre supprime.")
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE sessions SET project_id = NULL WHERE project_id = ?", (project_id,))
            result = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return result.rowcount > 0

    def linked_session_count(self, project_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM sessions WHERE project_id = ?", (project_id,)).fetchone()
        return int(row["count"])

    def permissions(self, project_id: str) -> list[ProjectPermission]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT id, project_id, permission, value_json FROM project_permissions WHERE project_id = ? ORDER BY permission",
                (project_id,),
            ).fetchall()
        return [ProjectPermission(row["id"], row["project_id"], row["permission"], row["value_json"]) for row in rows]

    def project_for_session(self, session_id: str | None) -> Project:
        project_id = DEFAULT_PROJECT_ID
        if session_id:
            with connect_runtime_db(self.config) as conn:
                row = conn.execute("SELECT project_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row and row["project_id"]:
                project_id = row["project_id"]
        project = self.get(project_id, include_disabled=False)
        if project is None:
            raise PermissionError("Projet introuvable, desactive ou inutilisable.")
        return project

    def _replace_permissions(self, conn, project_id: str, policy: dict) -> None:
        conn.execute("DELETE FROM project_permissions WHERE project_id = ?", (project_id,))
        for permission, value in sorted(policy.items()):
            conn.execute(
                "INSERT INTO project_permissions(id, project_id, permission, value_json) VALUES (?, ?, ?, ?)",
                (uuid4().hex, project_id, permission, json.dumps(value, ensure_ascii=False)),
            )

    def _from_row(self, row) -> Project:
        return Project(
            row["id"],
            row["name"],
            row["root_path"],
            row["description"],
            bool(row["enabled"]),
            row["created_at"],
            row["updated_at"],
            row["policy_json"],
            row["metadata_json"],
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
