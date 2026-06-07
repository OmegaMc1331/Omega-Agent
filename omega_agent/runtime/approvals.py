from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.reasoning import emit_reasoning_event
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action


@dataclass(frozen=True)
class Approval:
    id: str
    action: str
    arguments: dict
    risk: str
    status: str
    created_at: str
    resolved_at: str | None
    session_id: str | None = None
    action_type: str = "tool"
    tool_name: str = ""
    risk_level: str = "medium"
    reason: str = ""
    arguments_json: str = "{}"


class ApprovalsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self.init_db()

    def init_db(self) -> None:
        with connect_runtime_db(self.config):
            pass

    def create(
        self,
        action: str,
        arguments: dict,
        risk: str = "high",
        session_id: str | None = None,
        reason: str = "",
        action_type: str = "tool",
    ) -> Approval:
        now = datetime.now(timezone.utc).isoformat()
        approval = Approval(
            id=uuid4().hex,
            session_id=session_id,
            action=action,
            action_type=action_type,
            tool_name=action,
            arguments=arguments,
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            risk=risk,
            risk_level=risk,
            reason=reason,
            status="pending",
            created_at=now,
            resolved_at=None,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO approvals(
                    id, session_id, status, action_type, tool_name, arguments_json,
                    risk_level, reason, created_at, resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.session_id,
                    approval.status,
                    approval.action_type,
                    approval.tool_name,
                    approval.arguments_json,
                    approval.risk_level,
                    approval.reason,
                    approval.created_at,
                    approval.resolved_at,
                ),
            )
        self.events.add(
            "approval.required",
            {"approval_id": approval.id, "tool_name": action, "risk_level": risk, "reason": reason},
            session_id=session_id,
        )
        emit_reasoning_event(
            session_id or "",
            "reasoning.approval_required",
            "Approval requise",
            f"{action} nécessite une validation utilisateur.",
            status="pending",
            metadata={"approval_id": approval.id, "tool_name": action, "risk_level": risk, "reason": reason, "arguments": arguments},
            config=self.config,
        )
        log_action(self.config, "approval_required", {"approval_id": approval.id, "action": action, "risk": risk})
        return approval

    def list(self, status: str | None = None) -> list[Approval]:
        query = """
            SELECT id, session_id, status, action_type, tool_name, arguments_json,
                   risk_level, reason, created_at, resolved_at
            FROM approvals
        """
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def resolve(self, approval_id: str, approved: bool) -> Approval | None:
        status = "approved" if approved else "rejected"
        resolved_at = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
                (status, resolved_at, approval_id),
            )
            row = conn.execute(
                """
                SELECT id, session_id, status, action_type, tool_name, arguments_json,
                       risk_level, reason, created_at, resolved_at
                FROM approvals
                WHERE id = ?
                """,
                (approval_id,),
            ).fetchone()
        if not row:
            return None
        approval = self._from_row(row)
        self.events.add("approval.resolved", {"approval_id": approval.id, "status": approval.status}, session_id=approval.session_id)
        emit_reasoning_event(
            approval.session_id or "",
            "reasoning.approval_resolved",
            "Approval résolue",
            f"Approval {approval.status} pour {approval.tool_name}.",
            status="completed",
            metadata={"approval_id": approval.id, "status": approval.status, "tool_name": approval.tool_name},
            config=self.config,
        )
        log_action(self.config, "approval_resolved", {"approval_id": approval.id, "status": approval.status})
        return approval

    def _from_row(self, row) -> Approval:
        arguments_json = row["arguments_json"]
        arguments = json.loads(arguments_json)
        return Approval(
            id=row["id"],
            session_id=row["session_id"],
            action=row["tool_name"],
            action_type=row["action_type"],
            tool_name=row["tool_name"],
            arguments=arguments,
            arguments_json=arguments_json,
            risk=row["risk_level"],
            risk_level=row["risk_level"],
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )
