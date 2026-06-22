from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact, redact_text


class TraceCollector:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def collect_run_trace(self, run_id: str) -> dict:
        with connect_runtime_db(self.config) as conn:
            run = _fetch_one(conn, "SELECT * FROM runs WHERE id = ?", (run_id,))
            if run is None:
                raise ValueError("Run introuvable.")
            steps = _fetch_all(conn, "SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index ASC", (run_id,))
            actions = _fetch_all(conn, "SELECT * FROM action_journal WHERE run_id = ? ORDER BY created_at ASC", (run_id,))
            checkpoints = _fetch_all(conn, "SELECT id, run_id, step_id, label, created_at, metadata_json FROM checkpoints WHERE run_id = ? ORDER BY created_at ASC", (run_id,))
            snapshots = _fetch_all(conn, "SELECT * FROM file_snapshots WHERE run_id = ? ORDER BY created_at ASC", (run_id,))
            rollbacks = _fetch_all(conn, "SELECT * FROM rollback_events WHERE run_id = ? ORDER BY created_at ASC", (run_id,))
            events = _events_for_run(conn, run)
            reasoning = _reasoning_for_run(conn, run)
            outcome = _fetch_one(conn, "SELECT * FROM task_outcomes WHERE run_id = ? ORDER BY updated_at DESC LIMIT 1", (run_id,))
            metrics = _fetch_one(conn, "SELECT * FROM run_metrics WHERE run_id = ?", (run_id,))
        trace = {
            "run": run,
            "steps": steps,
            "actions": actions,
            "checkpoints": checkpoints,
            "snapshots": snapshots,
            "rollbacks": rollbacks,
            "events": events,
            "reasoning": reasoning,
            "outcome": outcome,
            "metrics": metrics,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.redact_trace(trace)

    def collect_session_traces(self, session_id: str) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT id FROM runs WHERE session_id = ? ORDER BY updated_at DESC LIMIT 50", (session_id,)).fetchall()
        return [self.collect_run_trace(row["id"]) for row in rows]

    def list_traces(self, limit: int = 100, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM runs"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            metrics = {
                row["run_id"]: dict(row)
                for row in conn.execute("SELECT * FROM run_metrics WHERE run_id IN (%s)" % ",".join("?" for _ in rows), tuple(row["id"] for row in rows)).fetchall()
            } if rows else {}
            outcomes = {
                row["run_id"]: dict(row)
                for row in conn.execute("SELECT * FROM task_outcomes WHERE run_id IN (%s) ORDER BY updated_at DESC" % ",".join("?" for _ in rows), tuple(row["id"] for row in rows)).fetchall()
            } if rows else {}
        return [
            redact(
                {
                    "run_id": row["id"],
                    "session_id": row["session_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "model_ref": row["model_ref"],
                    "agent_profile_id": row["active_agent_profile_id"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "updated_at": row["updated_at"],
                    "metrics": metrics.get(row["id"]),
                    "outcome": outcomes.get(row["id"]),
                }
            )
            for row in rows
        ]

    def redact_trace(self, trace: dict) -> dict:
        redacted = redact(trace)
        max_chars = max(1000, int(getattr(self.config, "evals_max_trace_chars", 20000) or 20000))
        text = json.dumps(redacted, ensure_ascii=False)
        if len(text) <= max_chars:
            return redacted
        compact = {
            "run": redacted.get("run"),
            "summary": self._summary_from_trace(redacted),
            "truncated": True,
            "max_trace_chars": max_chars,
        }
        return redact(compact)

    def export_trace_json(self, run_id: str) -> str:
        return json.dumps(self.collect_run_trace(run_id), ensure_ascii=False, indent=2) + "\n"

    def summarize_trace(self, run_id: str) -> dict:
        return self._summary_from_trace(self.collect_run_trace(run_id))

    def successful_trajectory_signals(self, limit: int = 100) -> list[dict]:
        signals = []
        for item in self.list_traces(limit=limit, status="succeeded"):
            trace = self.collect_run_trace(item["run_id"])
            summary = self._summary_from_trace(trace)
            outcome = trace.get("outcome") or {}
            signals.append(
                redact(
                    {
                        **summary,
                        "title": (trace.get("run") or {}).get("title"),
                        "user_feedback": outcome.get("user_feedback"),
                        "auto_score": outcome.get("auto_score"),
                        "human_score": outcome.get("human_score"),
                        "reusable": bool((trace.get("run") or {}).get("metadata", {}).get("reusable")),
                    }
                )
            )
        return signals

    def _summary_from_trace(self, trace: dict) -> dict:
        actions = trace.get("actions") or []
        rollbacks = trace.get("rollbacks") or []
        steps = trace.get("steps") or []
        failed_tools = [item for item in actions if item.get("status") == "failed"]
        denied = [item for item in actions if item.get("status") == "denied"]
        return redact(
            {
                "run_id": (trace.get("run") or {}).get("id"),
                "status": (trace.get("run") or {}).get("status"),
                "steps": len(steps),
                "tool_calls": len(actions),
                "failed_tool_calls": len(failed_tools),
                "denied_actions": len(denied),
                "rollbacks": len(rollbacks),
                "tools": sorted({str(item.get("tool_name") or "") for item in actions if item.get("tool_name")}),
            }
        )


def _fetch_one(conn, query: str, params: tuple = ()) -> dict | None:
    row = conn.execute(query, params).fetchone()
    return _row_to_dict(row) if row else None


def _fetch_all(conn, query: str, params: tuple = ()) -> list[dict]:
    return [_row_to_dict(row) for row in conn.execute(query, params).fetchall()]


def _row_to_dict(row) -> dict:
    result = dict(row)
    for key, value in list(result.items()):
        if key.endswith("_json") and isinstance(value, str):
            parsed_key = key[:-5]
            try:
                result[parsed_key] = json.loads(value or "{}")
            except json.JSONDecodeError:
                result[parsed_key] = redact_text(value)
    return redact(result)


def _events_for_run(conn, run: dict) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC LIMIT 500",
        (run.get("session_id"),),
    ).fetchall()
    result = []
    for row in rows:
        item = _row_to_dict(row)
        payload = item.get("payload") or {}
        if payload.get("run_id") == run.get("id") or item.get("type", "").startswith("run.") or item.get("type", "").startswith("action.") or item.get("type", "").startswith("rollback."):
            result.append(item)
    return result


def _reasoning_for_run(conn, run: dict) -> list[dict]:
    message_ids = [value for value in (run.get("user_message_id"), run.get("assistant_message_id")) if value]
    if message_ids:
        placeholders = ",".join("?" for _ in message_ids)
        rows = conn.execute(f"SELECT * FROM reasoning_events WHERE message_id IN ({placeholders}) ORDER BY created_at ASC", tuple(message_ids)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM reasoning_events WHERE session_id = ? ORDER BY created_at ASC LIMIT 100", (run.get("session_id"),)).fetchall()
    return [_row_to_dict(row) for row in rows if dict(row).get("visibility") != "internal"]
