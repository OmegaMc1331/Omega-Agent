from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

VALID_OUTCOMES = {"success", "partial", "failed", "blocked", "cancelled", "unknown"}


@dataclass(frozen=True)
class TaskOutcome:
    id: str
    run_id: str
    session_id: str | None
    project_id: str | None
    success: bool | None
    outcome: str
    user_feedback: str | None
    auto_score: float | None
    human_score: float | None
    reason: str | None
    created_at: str
    updated_at: str
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


class TaskOutcomesStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def record_auto_outcome(self, run_id: str, *, auto_score: float | None = None, outcome: str | None = None, reason: str | None = None, metadata: dict | None = None) -> TaskOutcome:
        run = self._run(run_id)
        status = run["status"]
        resolved = outcome or _outcome_from_status(status)
        success = True if resolved == "success" else False if resolved in {"failed", "blocked", "cancelled"} else None
        return self.upsert(
            run_id,
            session_id=run["session_id"],
            project_id=run["project_id"],
            success=success,
            outcome=resolved,
            auto_score=auto_score,
            reason=reason,
            metadata=metadata or {},
        )

    def update_outcome(
        self,
        run_id: str,
        outcome: str,
        *,
        user_feedback: str | None = None,
        human_score: float | None = None,
        reason: str | None = None,
    ) -> TaskOutcome:
        if outcome not in VALID_OUTCOMES:
            raise ValueError("Outcome invalide.")
        run = self._run(run_id)
        success = True if outcome == "success" else False if outcome in {"failed", "blocked", "cancelled"} else None
        return self.upsert(
            run_id,
            session_id=run["session_id"],
            project_id=run["project_id"],
            success=success,
            outcome=outcome,
            user_feedback=user_feedback,
            human_score=human_score,
            reason=reason,
        )

    def upsert(
        self,
        run_id: str,
        *,
        session_id: str | None,
        project_id: str | None,
        success: bool | None,
        outcome: str,
        user_feedback: str | None = None,
        auto_score: float | None = None,
        human_score: float | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> TaskOutcome:
        if outcome not in VALID_OUTCOMES:
            raise ValueError("Outcome invalide.")
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(redact(metadata or {}), ensure_ascii=False)
        with connect_runtime_db(self.config) as conn:
            existing = conn.execute("SELECT * FROM task_outcomes WHERE run_id = ? ORDER BY updated_at DESC LIMIT 1", (run_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE task_outcomes
                    SET session_id = ?, project_id = ?, success = ?, outcome = ?,
                        user_feedback = COALESCE(?, user_feedback),
                        auto_score = COALESCE(?, auto_score),
                        human_score = COALESCE(?, human_score),
                        reason = COALESCE(?, reason),
                        updated_at = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (
                        session_id,
                        project_id,
                        None if success is None else int(success),
                        outcome,
                        redact(user_feedback) if user_feedback is not None else None,
                        auto_score,
                        human_score,
                        redact(reason) if reason is not None else None,
                        now,
                        metadata_json,
                        existing["id"],
                    ),
                )
                row = conn.execute("SELECT * FROM task_outcomes WHERE id = ?", (existing["id"],)).fetchone()
                return _from_row(row)
            outcome_id = uuid4().hex
            conn.execute(
                """
                INSERT INTO task_outcomes(
                    id, run_id, session_id, project_id, success, outcome, user_feedback,
                    auto_score, human_score, reason, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    run_id,
                    session_id,
                    project_id,
                    None if success is None else int(success),
                    outcome,
                    redact(user_feedback),
                    auto_score,
                    human_score,
                    redact(reason),
                    now,
                    now,
                    metadata_json,
                ),
            )
        return self.get_by_run(run_id)

    def get_by_run(self, run_id: str) -> TaskOutcome | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM task_outcomes WHERE run_id = ? ORDER BY updated_at DESC LIMIT 1", (run_id,)).fetchone()
        return _from_row(row) if row else None

    def list(self, limit: int = 100) -> list[TaskOutcome]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM task_outcomes ORDER BY updated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [_from_row(row) for row in rows]

    def _run(self, run_id: str):
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("Run introuvable.")
        return row


def _outcome_from_status(status: str) -> str:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if status == "needs_approval":
        return "blocked"
    return "unknown"


def _from_row(row) -> TaskOutcome:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return TaskOutcome(
        id=row["id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        project_id=row["project_id"],
        success=None if row["success"] is None else bool(row["success"]),
        outcome=row["outcome"],
        user_feedback=row["user_feedback"],
        auto_score=row["auto_score"],
        human_score=row["human_score"],
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=metadata,
    )
