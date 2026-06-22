from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.memory_compaction import compact_project_memory
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action

ALLOWED_JOB_KINDS = {"summarize_session", "scan_workspace", "compact_memory", "memory_compaction", "run_scheduled_prompt", "project_health_check"}


@dataclass(frozen=True)
class Job:
    id: str
    title: str
    status: str
    kind: str
    input_json: str
    output_json: str
    logs_json: str
    created_at: str
    updated_at: str


class JobsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def create(self, title: str, kind: str, input_data: dict | None = None, run_now: bool = True) -> Job:
        if kind not in ALLOWED_JOB_KINDS:
            raise ValueError("Type de job non autorise.")
        now = utc_now()
        job = Job(uuid4().hex, title.strip() or kind, "queued", kind, json.dumps(input_data or {}, ensure_ascii=False), "{}", "[]", now, now)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO jobs(id, title, status, kind, input_json, output_json, logs_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job.id, job.title, job.status, job.kind, job.input_json, job.output_json, job.logs_json, job.created_at, job.updated_at),
            )
        self.events.add("job.created", {"job_id": job.id, "kind": kind})
        log_action(self.config, "job_created", {"job_id": job.id, "kind": kind})
        if run_now:
            return self.run(job.id) or job
        return job

    def list(self) -> list[Job]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT id, title, status, kind, input_json, output_json, logs_json, created_at, updated_at FROM jobs ORDER BY updated_at DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, job_id: str) -> Job | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT id, title, status, kind, input_json, output_json, logs_json, created_at, updated_at FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def run(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None or job.status in {"cancelled", "succeeded"}:
            return job
        self._update(job_id, "running", logs=["Job demarre."])
        input_data = json.loads(job.input_json)
        try:
            output, logs = self._execute(job.kind, input_data)
            self._update(job_id, "succeeded", output=output, logs=logs)
        except Exception as exc:  # defensive: jobs must not crash gateway
            self._update(job_id, "failed", output={"error": str(exc)}, logs=[str(exc)])
        updated = self.get(job_id)
        self.events.add("job.updated", {"job_id": job_id, "status": updated.status if updated else "unknown"})
        return updated

    def cancel(self, job_id: str) -> Job | None:
        self._update(job_id, "cancelled", logs=["Job annule."])
        self.events.add("job.updated", {"job_id": job_id, "status": "cancelled"})
        return self.get(job_id)

    def _execute(self, kind: str, input_data: dict) -> tuple[dict, list[str]]:
        if kind == "summarize_session":
            session_id = str(input_data.get("session_id") or "")
            messages = SessionsStore(self.config).list_messages(session_id) if session_id else []
            text = " ".join(message.content for message in messages[-20:])
            return {"summary": text[:1000], "messages": len(messages)}, ["Session resumee localement."]
        if kind == "scan_workspace":
            files = []
            for path in sorted(self.config.workspace.rglob("*")):
                if path.is_file() and ".omega" not in path.parts:
                    files.append(str(path.relative_to(self.config.workspace)))
                if len(files) >= 200:
                    break
            return {"files": files, "count": len(files)}, ["Workspace scanne sans lire les contenus."]
        if kind in {"memory_compaction", "compact_memory"}:
            project_id = str(input_data.get("project_id") or "default")
            result = compact_project_memory(self.config, project_id)
            return result, [f"Compaction memoire projet terminee pour {project_id}."]
        if kind == "run_scheduled_prompt":
            prompt = str(input_data.get("prompt") or "")
            session_id = str(input_data.get("session_id") or "")
            sessions = SessionsStore(self.config)
            if not session_id:
                session_id = sessions.create_session(str(input_data.get("title") or "Scheduled prompt")).id
            sessions.merge_metadata(session_id, {"scheduled_task": True, "scheduled": True, "task_id": input_data.get("task_id")})
            sessions.add_message(session_id, "user", prompt, metadata={"scheduled_task": True, "untrusted_input": False})
            return {"session_id": session_id, "prompt": prompt[:500], "scheduled": True}, ["Prompt planifie enregistre en session locale."]
        if kind == "project_health_check":
            files = []
            for path in sorted(self.config.workspace.rglob("*")):
                if path.is_file() and ".omega" not in path.parts:
                    files.append(str(path.relative_to(self.config.workspace)))
                if len(files) >= 50:
                    break
            return {"workspace": str(self.config.workspace), "sample_files": files, "count": len(files)}, ["Health check projet local sans actions sensibles."]
        raise ValueError("Type de job non autorise.")

    def _update(self, job_id: str, status: str, output: dict | None = None, logs: list[str] | None = None) -> None:
        now = utc_now()
        current = self.get(job_id)
        current_logs = json.loads(current.logs_json) if current else []
        current_logs.extend(logs or [])
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, output_json = ?, logs_json = ?, updated_at = ? WHERE id = ?",
                (status, json.dumps(output or {}, ensure_ascii=False), json.dumps(current_logs, ensure_ascii=False), now, job_id),
            )
        log_action(self.config, "job_updated", {"job_id": job_id, "status": status})

    def _from_row(self, row) -> Job:
        return Job(row["id"], row["title"], row["status"], row["kind"], row["input_json"], row["output_json"], row["logs_json"], row["created_at"], row["updated_at"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
