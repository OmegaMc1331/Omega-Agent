from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.skills.skill_models import SkillUsageEvent, parse_json


class SkillUsageStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def record(
        self,
        skill_id: str,
        *,
        run_id: str | None = None,
        status: str = "selected",
        success: bool | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SkillUsageEvent:
        event_id = uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO skill_usage_events(id, skill_id, run_id, status, success, duration_ms, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    skill_id,
                    run_id,
                    str(status)[:64],
                    None if success is None else (1 if success else 0),
                    duration_ms,
                    created_at,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        self.events.add("skill.used", {"skill_id": skill_id, "run_id": run_id, "status": status, "success": success})
        return self.get(event_id)

    def get(self, event_id: str) -> SkillUsageEvent | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM skill_usage_events WHERE id = ?", (event_id,)).fetchone()
        return _usage(row) if row else None

    def list(self, skill_id: str, limit: int = 200) -> list[SkillUsageEvent]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM skill_usage_events WHERE skill_id = ? ORDER BY created_at DESC LIMIT ?",
                (skill_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [_usage(row) for row in rows]

    def summary(self, skill_id: str) -> dict[str, Any]:
        events = self.list(skill_id)
        return {
            "count": len(events),
            "last_used": events[0].created_at if events else None,
            "success_count": sum(1 for item in events if item.success is True),
            "failure_count": sum(1 for item in events if item.success is False),
        }


def _usage(row) -> SkillUsageEvent:
    return SkillUsageEvent(
        id=row["id"],
        skill_id=row["skill_id"],
        run_id=row["run_id"],
        status=row["status"],
        success=None if row["success"] is None else bool(row["success"]),
        duration_ms=row["duration_ms"],
        created_at=row["created_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )
