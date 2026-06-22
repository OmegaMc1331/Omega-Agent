from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.action_journal import classify_action
from omega_agent.runtime.checkpoints import checkpoint_state, sanitize_checkpoint_state
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.replay import ReplayStore
from omega_agent.runtime.rollback import RollbackManager
from omega_agent.runtime.run_state import validate_action_status, validate_run_status, validate_step_status, validate_step_type
from omega_agent.runtime.self_healing import suggest_recovery
from omega_agent.runtime.snapshots import FileSnapshot, SnapshotStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class ApiRecord:
    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass(frozen=True)
class DurableRun(ApiRecord):
    id: str
    session_id: str
    title: str
    status: str
    user_message_id: str | None
    assistant_message_id: str | None
    active_agent_profile_id: str | None
    project_id: str | None
    model_ref: str | None
    started_at: str | None
    completed_at: str | None
    updated_at: str
    error: str | None
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


@dataclass(frozen=True)
class RunStep(ApiRecord):
    id: str
    run_id: str
    step_index: int
    type: str
    status: str
    title: str
    input: dict | None
    output: dict | None
    error: str | None
    started_at: str | None
    completed_at: str | None
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


@dataclass(frozen=True)
class RunAction(ApiRecord):
    id: str
    run_id: str
    step_id: str | None
    action_type: str
    tool_name: str | None
    arguments: dict
    policy_decision: dict
    budget_decision: dict
    risk_level: str
    status: str
    observation: dict | None
    created_at: str
    completed_at: str | None
    rollback_available: bool
    snapshot_id: str | None
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


class DurableRuntime:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self.snapshots = SnapshotStore(config)
        self.rollback = RollbackManager(config)
        self.replay = ReplayStore(config)

    def create_run(self, session_id: str, user_message: str, metadata: dict | None = None) -> DurableRun:
        now = _now()
        metadata = redact(metadata or {})
        run_id = uuid4().hex
        title = _title_from_message(user_message)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO runs(
                    id, session_id, title, status, user_message_id, assistant_message_id,
                    active_agent_profile_id, project_id, model_ref, started_at, completed_at,
                    updated_at, error, metadata_json
                )
                VALUES (?, ?, ?, 'pending', ?, NULL, ?, ?, ?, NULL, NULL, ?, NULL, ?)
                """,
                (
                    run_id,
                    session_id,
                    title,
                    metadata.get("user_message_id"),
                    metadata.get("active_agent_profile_id"),
                    metadata.get("project_id"),
                    metadata.get("model_ref"),
                    now,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
        self.events.add("run.created", {"run_id": run_id, "title": title, "status": "pending"}, session_id=session_id)
        self.create_checkpoint(
            run_id,
            "initial",
            checkpoint_state(
                self.config,
                run_id=run_id,
                session_id=session_id,
                active_agent_profile_id=metadata.get("active_agent_profile_id"),
                project_id=metadata.get("project_id"),
                model_ref=metadata.get("model_ref"),
                metadata={"phase": "initial"},
            ),
        )
        return self.get_run(run_id)

    def start_run(self, run_id: str) -> DurableRun:
        run = self._require_run(run_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE runs SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ?", (now, now, run_id))
        self.events.add("run.started", {"run_id": run_id, "status": "running"}, session_id=run.session_id)
        return self.get_run(run_id)

    def pause_run(self, run_id: str) -> DurableRun:
        return self._transition(run_id, "paused", "run.paused")

    def pause_run_for_budget(self, run_id: str, reason: str) -> DurableRun:
        run = self._require_run(run_id)
        metadata = {**run.metadata, "budget_pause_reason": redact(str(reason))}
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE runs SET status = 'paused', error = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (redact(str(reason)), json.dumps(redact(metadata), ensure_ascii=False), now, run_id),
            )
        self.events.add("budget.run.paused", {"run_id": run_id, "reason": redact(str(reason))}, session_id=run.session_id)
        return self.get_run(run_id)

    def resume_run(self, run_id: str) -> DurableRun:
        return self._transition(run_id, "running", "run.resumed")

    def cancel_run(self, run_id: str) -> DurableRun:
        run = self._require_run(run_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE runs SET status = 'cancelled', completed_at = ?, updated_at = ? WHERE id = ?", (now, now, run_id))
        self.events.add("run.cancelled", {"run_id": run_id, "status": "cancelled"}, session_id=run.session_id)
        self._post_run_eval(run_id)
        return self.get_run(run_id)

    def complete_run(self, run_id: str, final_response: str) -> DurableRun:
        run = self._require_run(run_id)
        if run.status in {"needs_approval", "paused", "cancelled"}:
            return run
        step = self.append_step(run_id, "final_response", "Reponse finale", input=None, status="running")
        self.complete_step(step.id, {"response": final_response})
        now = _now()
        metadata = {**run.metadata, "final_response": redact(final_response[:2000])}
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE runs SET status = 'succeeded', completed_at = ?, updated_at = ?, metadata_json = ? WHERE id = ?",
                (now, now, json.dumps(redact(metadata), ensure_ascii=False), run_id),
            )
        self.events.add("run.completed", {"run_id": run_id, "status": "succeeded"}, session_id=run.session_id)
        self._post_run_eval(run_id)
        return self.get_run(run_id)

    def fail_run(self, run_id: str, error: str) -> DurableRun:
        run = self._require_run(run_id)
        now = _now()
        suggestion = suggest_recovery(error)
        metadata = dict(run.metadata)
        if suggestion:
            metadata["self_healing"] = suggestion.as_api()
            self.events.add("self_healing.suggested", {"run_id": run_id, **suggestion.as_api()}, session_id=run.session_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE runs SET status = 'failed', completed_at = ?, updated_at = ?, error = ?, metadata_json = ? WHERE id = ?",
                (now, now, redact(str(error)), json.dumps(redact(metadata), ensure_ascii=False), run_id),
            )
        self.events.add("run.failed", {"run_id": run_id, "status": "failed", "error": redact(str(error))}, session_id=run.session_id)
        self._post_run_eval(run_id)
        return self.get_run(run_id)

    def set_run_message_ids(self, run_id: str, *, user_message_id: str | None = None, assistant_message_id: str | None = None) -> DurableRun:
        run = self._require_run(run_id)
        updates: list[str] = []
        params: list[object] = []
        if user_message_id is not None:
            updates.append("user_message_id = ?")
            params.append(user_message_id)
        if assistant_message_id is not None:
            updates.append("assistant_message_id = ?")
            params.append(assistant_message_id)
        if not updates:
            return run
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(run_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id = ?", tuple(params))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> DurableRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def list_runs(self, session_id: str | None = None, status: str | None = None, limit: int = 50) -> list[DurableRun]:
        query = "SELECT * FROM runs"
        clauses: list[str] = []
        params: list[object] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status:
            validate_run_status(status)
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 50), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_run_from_row(row) for row in rows]

    def append_step(self, run_id: str, type: str, title: str, input: dict | None = None, status: str = "pending") -> RunStep:
        run = self._require_run(run_id)
        validate_step_type(type)
        validate_step_status(status)
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT COALESCE(MAX(step_index), -1) + 1 AS next_index FROM run_steps WHERE run_id = ?", (run_id,)).fetchone()
            step_index = int(row["next_index"])
            step_id = uuid4().hex
            now = _now()
            conn.execute(
                """
                INSERT INTO run_steps(
                    id, run_id, step_index, type, status, title, input_json, output_json,
                    error, started_at, completed_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, '{}')
                """,
                (
                    step_id,
                    run_id,
                    step_index,
                    type,
                    status,
                    title,
                    json.dumps(redact(input), ensure_ascii=False) if input is not None else None,
                    now if status == "running" else None,
                ),
            )
            conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, run_id))
        self.events.add("step.created", {"run_id": run_id, "step_id": step_id, "type": type, "title": title, "status": status}, session_id=run.session_id)
        if status == "running":
            self.events.add("step.started", {"run_id": run_id, "step_id": step_id, "type": type}, session_id=run.session_id)
        return self.get_step(step_id)

    def get_step(self, step_id: str) -> RunStep | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM run_steps WHERE id = ?", (step_id,)).fetchone()
        return _step_from_row(row) if row else None

    def list_steps(self, run_id: str) -> list[RunStep]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index ASC", (run_id,)).fetchall()
        return [_step_from_row(row) for row in rows]

    def complete_step(self, step_id: str, output: dict | None = None) -> RunStep:
        step = self._require_step(step_id)
        run = self._require_run(step.run_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE run_steps SET status = 'succeeded', output_json = ?, completed_at = ? WHERE id = ?",
                (json.dumps(redact(output), ensure_ascii=False) if output is not None else None, now, step_id),
            )
            conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, step.run_id))
        self.events.add("step.completed", {"run_id": step.run_id, "step_id": step_id, "status": "succeeded"}, session_id=run.session_id)
        return self.get_step(step_id)

    def fail_step(self, step_id: str, error: str) -> RunStep:
        step = self._require_step(step_id)
        run = self._require_run(step.run_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE run_steps SET status = 'failed', error = ?, completed_at = ? WHERE id = ?", (redact(str(error)), now, step_id))
            conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, step.run_id))
        self.events.add("step.failed", {"run_id": step.run_id, "step_id": step_id, "error": redact(str(error))}, session_id=run.session_id)
        return self.get_step(step_id)

    def create_checkpoint(self, run_id: str, label: str, state: dict) -> dict:
        if not self.config.runtime_checkpoints_enabled:
            return {}
        run = self._require_run(run_id)
        checkpoint_id = uuid4().hex
        step_id = None
        now = _now()
        sanitized = sanitize_checkpoint_state(state)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO checkpoints(id, run_id, step_id, label, state_json, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, '{}')",
                (checkpoint_id, run_id, step_id, label, json.dumps(sanitized, ensure_ascii=False), now),
            )
        self.events.add("checkpoint.created", {"run_id": run_id, "checkpoint_id": checkpoint_id, "label": label}, session_id=run.session_id)
        return {"id": checkpoint_id, "run_id": run_id, "label": label, "state": sanitized, "created_at": now}

    def restore_checkpoint(self, run_id: str, checkpoint_id: str) -> dict:
        self._require_run(run_id)
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM checkpoints WHERE id = ? AND run_id = ?", (checkpoint_id, run_id)).fetchone()
        if row is None:
            raise ValueError("Checkpoint introuvable.")
        return {"id": row["id"], "run_id": row["run_id"], "label": row["label"], "state": json.loads(row["state_json"]), "created_at": row["created_at"]}

    def list_checkpoints(self, run_id: str) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM checkpoints WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        return [{"id": row["id"], "run_id": row["run_id"], "step_id": row["step_id"], "label": row["label"], "state": redact(json.loads(row["state_json"])), "created_at": row["created_at"], "metadata": json.loads(row["metadata_json"] or "{}")} for row in rows]

    def record_action(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict,
        policy_decision: Any,
        step_id: str | None = None,
        budget_decision: Any | None = None,
    ) -> RunAction:
        run = self._require_run(run_id)
        decision = _decision_to_dict(policy_decision)
        decision_status = {"allow": "allowed", "deny": "denied", "require_approval": "approval_required"}.get(str(decision.get("action") or decision.get("decision") or ""), "planned")
        status = validate_action_status(decision_status)
        action_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO action_journal(
                    id, run_id, step_id, action_type, tool_name, arguments_json,
                    policy_decision_json, budget_decision_json, risk_level, status, observation_json, created_at,
                    completed_at, rollback_available, snapshot_id, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, 0, NULL, '{}')
                """,
                (
                    action_id,
                    run_id,
                    step_id,
                    str(decision.get("action_category") or classify_action(tool_name, arguments)),
                    tool_name,
                    json.dumps(redact(arguments), ensure_ascii=False),
                    json.dumps(redact(decision), ensure_ascii=False),
                    json.dumps(redact(_budget_decision_to_dict(budget_decision)), ensure_ascii=False),
                    str(decision.get("risk_level") or "low"),
                    status,
                    now,
                ),
            )
            if status == "approval_required":
                conn.execute("UPDATE runs SET status = 'needs_approval', updated_at = ? WHERE id = ?", (now, run_id))
        self.events.add("action.planned", {"run_id": run_id, "action_id": action_id, "tool_name": tool_name, "status": status}, session_id=run.session_id)
        if status in {"allowed", "denied", "approval_required"}:
            event_suffix = "approval_required" if status == "approval_required" else status
            self.events.add(f"action.{event_suffix}", {"run_id": run_id, "action_id": action_id, "tool_name": tool_name, "risk_level": str(decision.get("risk_level") or "low")}, session_id=run.session_id)
        return self.get_action(action_id)

    def mark_action_running(self, action_id: str) -> RunAction:
        return self._update_action_status(action_id, "running")

    def mark_action_completed(self, action_id: str, observation: Any) -> RunAction:
        self.snapshots.update_hashes_after_action(action_id)
        action = self._require_action(action_id)
        now = _now()
        snapshot_id = action.snapshot_id
        rollback_available = bool(snapshot_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE action_journal SET status = 'succeeded', observation_json = ?, completed_at = ?, rollback_available = ? WHERE id = ?",
                (json.dumps(redact({"output": observation}), ensure_ascii=False), now, 1 if rollback_available else 0, action_id),
            )
        run = self._require_run(action.run_id)
        self.events.add("action.succeeded", {"run_id": action.run_id, "action_id": action_id, "tool_name": action.tool_name}, session_id=run.session_id)
        return self.get_action(action_id)

    def mark_action_failed(self, action_id: str, error: str) -> RunAction:
        action = self._require_action(action_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE action_journal SET status = 'failed', observation_json = ?, completed_at = ? WHERE id = ?",
                (json.dumps(redact({"error": str(error)}), ensure_ascii=False), now, action_id),
            )
        run = self._require_run(action.run_id)
        self.events.add("action.failed", {"run_id": action.run_id, "action_id": action_id, "tool_name": action.tool_name, "error": redact(str(error))}, session_id=run.session_id)
        suggestion = suggest_recovery(error)
        if suggestion:
            self.events.add("self_healing.suggested", {"run_id": action.run_id, "action_id": action_id, **suggestion.as_api()}, session_id=run.session_id)
        return self.get_action(action_id)

    def get_action(self, action_id: str) -> RunAction | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM action_journal WHERE id = ?", (action_id,)).fetchone()
        return _action_from_row(row) if row else None

    def list_actions(self, run_id: str) -> list[RunAction]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM action_journal WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        return [_action_from_row(row) for row in rows]

    def create_snapshot_for_paths(self, run_id: str, action_id: str | None, paths: list[str]) -> list[FileSnapshot]:
        snapshots = self.snapshots.create_for_paths(run_id, action_id, paths)
        return snapshots

    def list_snapshots(self, run_id: str | None = None, limit: int = 100) -> list[FileSnapshot]:
        return self.snapshots.list(run_id=run_id, limit=limit)

    def rollback_snapshot(self, snapshot_id: str) -> dict:
        return self.rollback.rollback_snapshot(snapshot_id).as_api()

    def rollback_run(self, run_id: str) -> dict:
        self._require_run(run_id)
        return self.rollback.rollback_run(run_id)

    def replay_run(self, run_id: str, dry_run: bool = True) -> dict:
        run = self._require_run(run_id)
        self.events.add("replay.started", {"run_id": run_id, "dry_run": dry_run}, session_id=run.session_id)
        result = self.replay.replay_run(run_id, dry_run=dry_run)
        self.events.add("replay.completed", {"run_id": run_id, "dry_run": dry_run}, session_id=run.session_id)
        return result

    def recover_interrupted_runs(self) -> list[DurableRun]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(60, int(self.config.runtime_max_run_seconds)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM runs WHERE status = 'running'").fetchall()
        recovered: list[DurableRun] = []
        for row in rows:
            run = _run_from_row(row)
            updated = _parse_dt(run.updated_at)
            if updated and updated > cutoff:
                continue
            if self.config.runtime_resume_interrupted_runs:
                recovered.append(self._transition(run.id, "paused", "run.recovered", reason="crash_recovery"))
            else:
                recovered.append(self.fail_run(run.id, "crash_recovery"))
        return recovered

    def _transition(self, run_id: str, status: str, event_type: str, reason: str | None = None) -> DurableRun:
        validate_run_status(status)
        run = self._require_run(run_id)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (status, now, run_id))
        payload = {"run_id": run_id, "status": status}
        if reason:
            payload["reason"] = reason
        self.events.add(event_type, payload, session_id=run.session_id)
        return self.get_run(run_id)

    def _update_action_status(self, action_id: str, status: str) -> RunAction:
        validate_action_status(status)
        action = self._require_action(action_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE action_journal SET status = ? WHERE id = ?", (status, action_id))
        return self.get_action(action_id)

    def _require_run(self, run_id: str) -> DurableRun:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError("Run introuvable.")
        return run

    def _require_step(self, step_id: str) -> RunStep:
        step = self.get_step(step_id)
        if step is None:
            raise ValueError("Step introuvable.")
        return step

    def _require_action(self, action_id: str) -> RunAction:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError("Action introuvable.")
        return action

    def _post_run_eval(self, run_id: str) -> None:
        if self.config.evals_enabled:
            try:
                if self.config.evals_collect_metrics:
                    from omega_agent.evals.metrics import MetricsStore

                    MetricsStore(self.config).compute_run_metrics(run_id)
                if self.config.evals_auto_score_runs:
                    from omega_agent.evals.run_scoring import RunScoring

                    RunScoring(self.config).score_run(run_id)
                if self.config.evals_failure_clustering_enabled:
                    from omega_agent.evals.failure_clustering import FailureClustering

                    FailureClustering(self.config).cluster_recent_failures(limit=50)
            except Exception as exc:
                run = self.get_run(run_id)
                self.events.add("eval.error", {"run_id": run_id, "error": redact(str(exc))}, session_id=run.session_id if run else None)
        if getattr(self.config, "skills_auto_detect_candidates", False) and getattr(self.config, "skills_foundry_enabled", True):
            try:
                from omega_agent.skills.foundry import SkillFoundry

                SkillFoundry(self.config).detect_candidates(limit=100)
            except Exception as exc:
                run = self.get_run(run_id)
                self.events.add("skill.foundry.error", {"run_id": run_id, "error": redact(str(exc))}, session_id=run.session_id if run else None)


def _run_from_row(row) -> DurableRun:
    return DurableRun(
        id=row["id"],
        session_id=row["session_id"],
        title=row["title"],
        status=row["status"],
        user_message_id=row["user_message_id"],
        assistant_message_id=row["assistant_message_id"],
        active_agent_profile_id=row["active_agent_profile_id"],
        project_id=row["project_id"],
        model_ref=row["model_ref"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
        error=row["error"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _step_from_row(row) -> RunStep:
    return RunStep(
        id=row["id"],
        run_id=row["run_id"],
        step_index=int(row["step_index"]),
        type=row["type"],
        status=row["status"],
        title=row["title"],
        input=json.loads(row["input_json"]) if row["input_json"] else None,
        output=json.loads(row["output_json"]) if row["output_json"] else None,
        error=row["error"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _action_from_row(row) -> RunAction:
    return RunAction(
        id=row["id"],
        run_id=row["run_id"],
        step_id=row["step_id"],
        action_type=row["action_type"],
        tool_name=row["tool_name"],
        arguments=json.loads(row["arguments_json"] or "{}"),
        policy_decision=json.loads(row["policy_decision_json"] or "{}"),
        budget_decision=json.loads(row["budget_decision_json"] or "{}"),
        risk_level=row["risk_level"],
        status=row["status"],
        observation=json.loads(row["observation_json"]) if row["observation_json"] else None,
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        rollback_available=bool(row["rollback_available"]),
        snapshot_id=row["snapshot_id"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _decision_to_dict(policy_decision: Any) -> dict:
    if isinstance(policy_decision, dict):
        return redact(policy_decision)
    return redact(
        {
            "action": getattr(policy_decision, "action", getattr(policy_decision, "decision", "planned")),
            "decision": getattr(policy_decision, "decision", getattr(policy_decision, "action", "planned")),
            "reason": getattr(policy_decision, "reason", ""),
            "risk_level": getattr(policy_decision, "risk_level", "low"),
            "redacted_arguments": getattr(policy_decision, "redacted_arguments", None),
            "matched_rules": getattr(policy_decision, "matched_rules", None),
            "warnings": getattr(policy_decision, "warnings", None),
            "action_category": getattr(policy_decision, "action_category", None),
            "budget_decision": getattr(policy_decision, "budget_decision", None),
            "shadow_required": getattr(policy_decision, "shadow_required", False),
        }
    )


def _budget_decision_to_dict(decision: Any | None) -> dict:
    if decision is None:
        return {}
    if isinstance(decision, dict):
        return redact(decision)
    if hasattr(decision, "as_api"):
        return redact(decision.as_api())
    return redact({"action": getattr(decision, "action", ""), "reason": getattr(decision, "reason", "")})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _title_from_message(message: str) -> str:
    title = " ".join(str(message or "").strip().split())
    if not title:
        return "Run manuel"
    return title[:80]
