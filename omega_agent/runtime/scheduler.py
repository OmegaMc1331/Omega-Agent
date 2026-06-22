from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.context import current_runtime_mode
from omega_agent.runtime.jobs import JobsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action

VALID_SCHEDULE_TYPES = {"once", "interval", "cron"}


@dataclass(frozen=True)
class ScheduledTask:
    id: str
    title: str
    prompt: str
    schedule_type: str
    schedule_value: str
    enabled: bool
    next_run_at: str | None
    last_run_at: str | None
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


class ScheduledTasksStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def create(
        self,
        title: str,
        prompt: str,
        schedule_type: str = "once",
        schedule_value: str = "",
        enabled: bool = True,
        metadata: dict | None = None,
    ) -> ScheduledTask:
        if schedule_type not in VALID_SCHEDULE_TYPES:
            raise ValueError("Type de schedule invalide.")
        if not prompt.strip():
            raise ValueError("Prompt planifie vide.")
        now = utc_now()
        task = ScheduledTask(
            id=uuid4().hex,
            title=title.strip() or "Scheduled task",
            prompt=prompt.strip(),
            schedule_type=schedule_type,
            schedule_value=schedule_value.strip(),
            enabled=enabled,
            next_run_at=compute_next_run(schedule_type, schedule_value, from_dt=datetime.now(timezone.utc)) if enabled else None,
            last_run_at=None,
            created_at=now,
            updated_at=now,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO scheduled_tasks(
                    id, title, prompt, schedule_type, schedule_value, enabled,
                    next_run_at, last_run_at, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.title,
                    task.prompt,
                    task.schedule_type,
                    task.schedule_value,
                    int(task.enabled),
                    task.next_run_at,
                    task.last_run_at,
                    task.created_at,
                    task.updated_at,
                    task.metadata_json,
                ),
            )
        log_action(self.config, "scheduled_task_created", {"task_id": task.id})
        return task

    def list(self) -> list[ScheduledTask]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT id, title, prompt, schedule_type, schedule_value, enabled,
                       next_run_at, last_run_at, created_at, updated_at, metadata_json
                FROM scheduled_tasks
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def due(self, now: datetime | None = None) -> list[ScheduledTask]:
        current = (now or datetime.now(timezone.utc)).isoformat()
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT id, title, prompt, schedule_type, schedule_value, enabled,
                       next_run_at, last_run_at, created_at, updated_at, metadata_json
                FROM scheduled_tasks
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (current,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, task_id: str) -> ScheduledTask | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT id, title, prompt, schedule_type, schedule_value, enabled,
                       next_run_at, last_run_at, created_at, updated_at, metadata_json
                FROM scheduled_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def update(
        self,
        task_id: str,
        title: str | None = None,
        prompt: str | None = None,
        schedule_type: str | None = None,
        schedule_value: str | None = None,
        enabled: bool | None = None,
        metadata: dict | None = None,
    ) -> ScheduledTask | None:
        current = self.get(task_id)
        if current is None:
            return None
        next_type = schedule_type or current.schedule_type
        if next_type not in VALID_SCHEDULE_TYPES:
            raise ValueError("Type de schedule invalide.")
        next_enabled = current.enabled if enabled is None else enabled
        next_value = schedule_value if schedule_value is not None else current.schedule_value
        next_run = compute_next_run(next_type, next_value, from_dt=datetime.now(timezone.utc)) if next_enabled else None
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET title = ?, prompt = ?, schedule_type = ?, schedule_value = ?, enabled = ?,
                    next_run_at = ?, updated_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    title.strip() if title is not None and title.strip() else current.title,
                    prompt.strip() if prompt is not None and prompt.strip() else current.prompt,
                    next_type,
                    next_value,
                    int(next_enabled),
                    next_run,
                    now,
                    json.dumps(metadata if metadata is not None else current.metadata, ensure_ascii=False),
                    task_id,
                ),
            )
        log_action(self.config, "scheduled_task_updated", {"task_id": task_id})
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        if result.rowcount:
            log_action(self.config, "scheduled_task_deleted", {"task_id": task_id})
        return result.rowcount > 0

    def run_now(self, task_id: str) -> tuple[ScheduledTask, object]:
        task = self.get(task_id)
        if task is None:
            raise ValueError("Tache planifiee introuvable.")
        if not task.enabled:
            raise PermissionError("Tache planifiee desactivee.")
        job = JobsStore(self.config).create(
            task.title,
            "run_scheduled_prompt",
            {"task_id": task.id, "prompt": task.prompt, "metadata": task.metadata, "scheduled": True},
            run_now=True,
        )
        self.mark_ran(task)
        log_action(self.config, "scheduled_task_run_now", {"task_id": task.id, "job_id": job.id})
        return self.get(task.id), job

    def mark_ran(self, task: ScheduledTask) -> None:
        now_dt = datetime.now(timezone.utc)
        if task.schedule_type == "once":
            next_run = None
            enabled = 0
        else:
            next_run = compute_next_run(task.schedule_type, task.schedule_value, from_dt=now_dt)
            enabled = int(task.enabled)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE scheduled_tasks SET last_run_at = ?, next_run_at = ?, enabled = ?, updated_at = ? WHERE id = ?",
                (now_dt.isoformat(), next_run, enabled, now_dt.isoformat(), task.id),
            )

    def _from_row(self, row) -> ScheduledTask:
        return ScheduledTask(
            row["id"],
            row["title"],
            row["prompt"],
            row["schedule_type"],
            row["schedule_value"],
            bool(row["enabled"]),
            row["next_run_at"],
            row["last_run_at"],
            row["created_at"],
            row["updated_at"],
            row["metadata_json"],
        )


class SchedulerLoop:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.tasks = ScheduledTasksStore(config)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if current_runtime_mode() != "server" or not self.config.scheduler_enabled:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="omega-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            try:
                for task in self.tasks.due():
                    try:
                        self.tasks.run_now(task.id)
                    except Exception as exc:
                        log_action(self.config, "scheduled_task_error", {"task_id": task.id, "reason": str(exc)})
                await asyncio.sleep(self.config.scheduler_tick_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_action(self.config, "scheduler_error", {"reason": str(exc)})
                await asyncio.sleep(self.config.scheduler_tick_seconds)


def compute_next_run(schedule_type: str, schedule_value: str, from_dt: datetime | None = None) -> str | None:
    base = from_dt or datetime.now(timezone.utc)
    if schedule_type == "once":
        if schedule_value:
            return _parse_datetime(schedule_value).isoformat()
        return base.isoformat()
    if schedule_type == "interval":
        seconds = int(schedule_value or "60")
        if seconds < 5:
            seconds = 5
        return (base + timedelta(seconds=seconds)).isoformat()
    if schedule_type == "cron":
        # v0 supports minute-level cron placeholders by scheduling the next minute.
        return (base + timedelta(minutes=1)).isoformat()
    raise ValueError("Type de schedule invalide.")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
