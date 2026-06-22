from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.workflows.workflow_models import (
    WORKFLOW_STATUSES,
    WORKFLOW_STEP_STATUSES,
    Workflow,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowTemplate,
    parse_json,
)
from omega_agent.workflows.workflow_templates import builtin_workflow_templates, template_created_at


class WorkflowStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self.ensure_builtin_templates()

    def ensure_builtin_templates(self) -> None:
        if not self.config.workflows_templates_enabled:
            return
        now = template_created_at()
        with connect_runtime_db(self.config) as conn:
            for template in builtin_workflow_templates():
                conn.execute(
                    """
                    INSERT INTO workflow_templates(id, name, description, category, definition_json, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        category = excluded.category,
                        definition_json = excluded.definition_json,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        template["id"],
                        template["name"],
                        template.get("description", ""),
                        template.get("category", "general"),
                        json.dumps(redact(template["definition"]), ensure_ascii=False),
                        now,
                        json.dumps(redact(template.get("metadata") or {}), ensure_ascii=False),
                    ),
                )

    def create_workflow(self, definition: dict[str, Any], *, enabled: bool = True, metadata: dict[str, Any] | None = None) -> Workflow:
        now = _now()
        workflow_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO workflows(id, name, description, version, enabled, definition_json, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    str(definition.get("name") or "Workflow"),
                    str(definition.get("description") or ""),
                    str(definition.get("version") or "1.0"),
                    1 if enabled else 0,
                    json.dumps(redact(definition), ensure_ascii=False),
                    now,
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        self.events.add("workflow.created", {"workflow_id": workflow_id, "name": definition.get("name")})
        return self.get_workflow(workflow_id)

    def update_workflow(self, workflow_id: str, patch: dict[str, Any]) -> Workflow | None:
        current = self.get_workflow(workflow_id)
        if current is None:
            return None
        definition = patch.get("definition") if isinstance(patch.get("definition"), dict) else current.definition
        name = str(patch.get("name") or definition.get("name") or current.name)
        description = str(patch.get("description") or definition.get("description") or current.description)
        version = str(patch.get("version") or definition.get("version") or current.version)
        enabled = current.enabled if "enabled" not in patch else bool(patch["enabled"])
        metadata = patch.get("metadata") if isinstance(patch.get("metadata"), dict) else current.metadata
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE workflows
                SET name = ?, description = ?, version = ?, enabled = ?, definition_json = ?, updated_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    name,
                    description,
                    version,
                    1 if enabled else 0,
                    json.dumps(redact(definition), ensure_ascii=False),
                    now,
                    json.dumps(redact(metadata), ensure_ascii=False),
                    workflow_id,
                ),
            )
        self.events.add("workflow.updated", {"workflow_id": workflow_id, "name": name})
        return self.get_workflow(workflow_id)

    def delete_workflow(self, workflow_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        return cursor.rowcount > 0

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        return _workflow_from_row(row) if row else None

    def find_workflow(self, identifier: str) -> Workflow | None:
        workflow = self.get_workflow(identifier)
        if workflow:
            return workflow
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM workflows WHERE lower(name) = lower(?) ORDER BY updated_at DESC LIMIT 1", (identifier,)).fetchone()
        return _workflow_from_row(row) if row else None

    def list_workflows(self, *, enabled: bool | None = None, limit: int = 100) -> list[Workflow]:
        query = "SELECT * FROM workflows"
        params: list[Any] = []
        if enabled is not None:
            query += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_workflow_from_row(row) for row in rows]

    def list_templates(self, category: str | None = None) -> list[WorkflowTemplate]:
        self.ensure_builtin_templates()
        query = "SELECT * FROM workflow_templates"
        params: list[Any] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY category ASC, name ASC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_template_from_row(row) for row in rows]

    def create_template(
        self,
        *,
        template_id: str,
        name: str,
        description: str,
        category: str,
        definition: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowTemplate:
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO workflow_templates(id, name, description, category, definition_json, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    category = excluded.category,
                    definition_json = excluded.definition_json,
                    metadata_json = excluded.metadata_json
                """,
                (
                    template_id,
                    name,
                    description,
                    category,
                    json.dumps(redact(definition), ensure_ascii=False),
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        return self.get_template(template_id)

    def get_template(self, template_id_or_name: str) -> WorkflowTemplate | None:
        self.ensure_builtin_templates()
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM workflow_templates WHERE id = ? OR lower(name) = lower(?) LIMIT 1",
                (template_id_or_name, template_id_or_name),
            ).fetchone()
        return _template_from_row(row) if row else None

    def create_run(self, workflow_id: str, run_id: str | None, input: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> WorkflowRun:
        now = _now()
        workflow_run_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs(
                    id, workflow_id, run_id, status, input_json, output_json,
                    current_step_index, started_at, completed_at, created_at, updated_at, error, metadata_json
                )
                VALUES (?, ?, ?, 'pending', ?, NULL, 0, NULL, NULL, ?, ?, NULL, ?)
                """,
                (
                    workflow_run_id,
                    workflow_id,
                    run_id,
                    json.dumps(redact(input or {}), ensure_ascii=False),
                    now,
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        return self.get_run(workflow_run_id)

    def list_runs(self, *, workflow_id: str | None = None, status: str | None = None, limit: int = 100) -> list[WorkflowRun]:
        query = "SELECT * FROM workflow_runs"
        clauses: list[str] = []
        params: list[Any] = []
        if workflow_id:
            clauses.append("workflow_id = ?")
            params.append(workflow_id)
        if status:
            _validate_status(status, WORKFLOW_STATUSES, "workflow run")
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_run_from_row(row) for row in rows]

    def get_run(self, workflow_run_id: str) -> WorkflowRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (workflow_run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def update_run(
        self,
        workflow_run_id: str,
        *,
        status: str | None = None,
        current_step_index: int | None = None,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        started: bool = False,
        completed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        current = self.require_run(workflow_run_id)
        if status is not None:
            _validate_status(status, WORKFLOW_STATUSES, "workflow run")
        next_metadata = current.metadata if metadata is None else metadata
        now = _now()
        started_at = current.started_at or now if started else current.started_at
        completed_at = now if completed else current.completed_at
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE workflow_runs
                SET status = ?, current_step_index = ?, output_json = ?, error = ?,
                    started_at = ?, completed_at = ?, updated_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    status or current.status,
                    current.current_step_index if current_step_index is None else int(current_step_index),
                    json.dumps(redact(output), ensure_ascii=False) if output is not None else (json.dumps(redact(current.output), ensure_ascii=False) if current.output is not None else None),
                    redact(error) if error is not None else current.error,
                    started_at,
                    completed_at,
                    now,
                    json.dumps(redact(next_metadata), ensure_ascii=False),
                    workflow_run_id,
                ),
            )
        return self.get_run(workflow_run_id)

    def create_step_run(self, workflow_run_id: str, step_index: int, definition: dict[str, Any]) -> WorkflowStepRun:
        now = _now()
        step_run_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO workflow_step_runs(
                    id, workflow_run_id, step_id, step_index, name, type, status,
                    input_json, output_json, error, started_at, completed_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    step_run_id,
                    workflow_run_id,
                    str(definition.get("id")),
                    step_index,
                    str(definition.get("name") or definition.get("id")),
                    str(definition.get("type")),
                    json.dumps(redact(definition), ensure_ascii=False),
                    json.dumps(redact({"definition": definition, "created_at": now}), ensure_ascii=False),
                ),
            )
        return self.get_step_run(step_run_id)

    def get_step_run(self, step_run_id: str) -> WorkflowStepRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM workflow_step_runs WHERE id = ?", (step_run_id,)).fetchone()
        return _step_from_row(row) if row else None

    def get_step_run_by_step_id(self, workflow_run_id: str, step_id: str) -> WorkflowStepRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM workflow_step_runs WHERE workflow_run_id = ? AND step_id = ? ORDER BY step_index ASC LIMIT 1",
                (workflow_run_id, step_id),
            ).fetchone()
        return _step_from_row(row) if row else None

    def list_step_runs(self, workflow_run_id: str) -> list[WorkflowStepRun]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_step_runs WHERE workflow_run_id = ? ORDER BY step_index ASC",
                (workflow_run_id,),
            ).fetchall()
        return [_step_from_row(row) for row in rows]

    def update_step_run(
        self,
        step_run_id: str,
        *,
        status: str | None = None,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        started: bool = False,
        completed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowStepRun:
        current = self.require_step_run(step_run_id)
        if status is not None:
            _validate_status(status, WORKFLOW_STEP_STATUSES, "workflow step")
        now = _now()
        next_metadata = current.metadata if metadata is None else metadata
        started_at = current.started_at or now if started else current.started_at
        completed_at = now if completed else current.completed_at
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE workflow_step_runs
                SET status = ?, output_json = ?, error = ?, started_at = ?, completed_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    status or current.status,
                    json.dumps(redact(output), ensure_ascii=False) if output is not None else (json.dumps(redact(current.output), ensure_ascii=False) if current.output is not None else None),
                    redact(error) if error is not None else current.error,
                    started_at,
                    completed_at,
                    json.dumps(redact(next_metadata), ensure_ascii=False),
                    step_run_id,
                ),
            )
        return self.get_step_run(step_run_id)

    def require_workflow(self, workflow_id: str) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError("Workflow introuvable.")
        return workflow

    def require_run(self, workflow_run_id: str) -> WorkflowRun:
        run = self.get_run(workflow_run_id)
        if run is None:
            raise ValueError("Workflow run introuvable.")
        return run

    def require_step_run(self, step_run_id: str) -> WorkflowStepRun:
        step = self.get_step_run(step_run_id)
        if step is None:
            raise ValueError("Workflow step run introuvable.")
        return step


def _workflow_from_row(row) -> Workflow:
    return Workflow(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        version=row["version"],
        enabled=bool(row["enabled"]),
        definition=parse_json(row["definition_json"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _run_from_row(row) -> WorkflowRun:
    return WorkflowRun(
        id=row["id"],
        workflow_id=row["workflow_id"],
        run_id=row["run_id"],
        status=row["status"],
        input=parse_json(row["input_json"], {}),
        output=parse_json(row["output_json"], None),
        current_step_index=int(row["current_step_index"] or 0),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row["error"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _step_from_row(row) -> WorkflowStepRun:
    return WorkflowStepRun(
        id=row["id"],
        workflow_run_id=row["workflow_run_id"],
        step_id=row["step_id"],
        step_index=int(row["step_index"]),
        name=row["name"],
        type=row["type"],
        status=row["status"],
        input=parse_json(row["input_json"], None),
        output=parse_json(row["output_json"], None),
        error=row["error"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _template_from_row(row) -> WorkflowTemplate:
    return WorkflowTemplate(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        category=row["category"],
        definition=parse_json(row["definition_json"], {}),
        created_at=row["created_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _validate_status(value: str, allowed: set[str], subject: str) -> None:
    if value not in allowed:
        raise ValueError(f"Statut {subject} invalide: {value}.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
