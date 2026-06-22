from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class RunMetrics:
    id: str
    run_id: str
    total_duration_ms: int
    first_event_ms: int | None
    first_token_ms: int | None
    tool_calls_count: int
    failed_tool_calls_count: int
    approvals_count: int
    rollbacks_count: int
    files_changed_count: int
    shell_commands_count: int
    model_ref: str | None
    agent_profile_id: str | None
    estimated_cost: float | None
    risk_max: str | None
    budget_violations_count: int
    budget_efficiency: float | None
    created_at: str
    metadata: dict

    def as_api(self) -> dict:
        return redact(self.__dict__)


class MetricsStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def compute_run_metrics(self, run_id: str) -> RunMetrics:
        with connect_runtime_db(self.config) as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Run introuvable.")
            actions = conn.execute("SELECT * FROM action_journal WHERE run_id = ?", (run_id,)).fetchall()
            rollbacks = conn.execute("SELECT * FROM rollback_events WHERE run_id = ?", (run_id,)).fetchall()
            snapshots = conn.execute("SELECT * FROM file_snapshots WHERE run_id = ?", (run_id,)).fetchall()
            events = conn.execute("SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC", (run["session_id"],)).fetchall()
            budget_violations = conn.execute("SELECT COUNT(*) AS c FROM budget_violations WHERE run_id = ?", (run_id,)).fetchone()["c"]
            budget_usage = conn.execute("SELECT used_value, limit_value FROM budget_usage WHERE run_id = ? AND limit_value IS NOT NULL", (run_id,)).fetchall()
        started_at = _parse_dt(run["started_at"]) or _parse_dt(run["updated_at"]) or datetime.now(timezone.utc)
        completed_at = _parse_dt(run["completed_at"]) or _parse_dt(run["updated_at"]) or started_at
        event_times = [_parse_dt(row["created_at"]) for row in events if _event_matches_run(row, run_id)]
        event_times = [item for item in event_times if item is not None]
        first_event_ms = _delta_ms(started_at, min(event_times)) if event_times else None
        first_token_ms = _first_token_ms(events, run_id, started_at)
        failed = [row for row in actions if row["status"] == "failed"]
        approvals = [row for row in actions if row["status"] == "approval_required"]
        shell_commands = [row for row in actions if row["tool_name"] == "run_shell"]
        risks = [str(row["risk_level"] or "low") for row in actions]
        risk_max = max(risks, key=lambda value: RISK_ORDER.get(value, 0)) if risks else None
        metadata = {
            "run_status": run["status"],
            "denied_actions": sum(1 for row in actions if row["status"] == "denied"),
            "tools": sorted({str(row["tool_name"]) for row in actions if row["tool_name"]}),
            "budget_violations": int(budget_violations or 0),
        }
        budget_ratios = [
            min(1.0, float(row["used_value"] or 0) / float(row["limit_value"]))
            for row in budget_usage
            if float(row["limit_value"] or 0) > 0
        ]
        budget_efficiency = round(1.0 - (sum(budget_ratios) / len(budget_ratios)), 3) if budget_ratios else None
        metrics = RunMetrics(
            id=uuid4().hex,
            run_id=run_id,
            total_duration_ms=max(0, _delta_ms(started_at, completed_at)),
            first_event_ms=first_event_ms,
            first_token_ms=first_token_ms,
            tool_calls_count=len(actions),
            failed_tool_calls_count=len(failed),
            approvals_count=len(approvals),
            rollbacks_count=len(rollbacks),
            files_changed_count=len(snapshots),
            shell_commands_count=len(shell_commands),
            model_ref=run["model_ref"] or _metadata_value(run["metadata_json"], "model_ref"),
            agent_profile_id=run["active_agent_profile_id"],
            estimated_cost=None,
            risk_max=risk_max,
            budget_violations_count=int(budget_violations or 0),
            budget_efficiency=budget_efficiency,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=redact(metadata),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO run_metrics(
                    id, run_id, total_duration_ms, first_event_ms, first_token_ms,
                    tool_calls_count, failed_tool_calls_count, approvals_count, rollbacks_count,
                    files_changed_count, shell_commands_count, model_ref, agent_profile_id,
                    estimated_cost, risk_max, budget_violations_count, budget_efficiency, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    total_duration_ms=excluded.total_duration_ms,
                    first_event_ms=excluded.first_event_ms,
                    first_token_ms=excluded.first_token_ms,
                    tool_calls_count=excluded.tool_calls_count,
                    failed_tool_calls_count=excluded.failed_tool_calls_count,
                    approvals_count=excluded.approvals_count,
                    rollbacks_count=excluded.rollbacks_count,
                    files_changed_count=excluded.files_changed_count,
                    shell_commands_count=excluded.shell_commands_count,
                    model_ref=excluded.model_ref,
                    agent_profile_id=excluded.agent_profile_id,
                    estimated_cost=excluded.estimated_cost,
                    risk_max=excluded.risk_max,
                    budget_violations_count=excluded.budget_violations_count,
                    budget_efficiency=excluded.budget_efficiency,
                    created_at=excluded.created_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    metrics.id,
                    metrics.run_id,
                    metrics.total_duration_ms,
                    metrics.first_event_ms,
                    metrics.first_token_ms,
                    metrics.tool_calls_count,
                    metrics.failed_tool_calls_count,
                    metrics.approvals_count,
                    metrics.rollbacks_count,
                    metrics.files_changed_count,
                    metrics.shell_commands_count,
                    metrics.model_ref,
                    metrics.agent_profile_id,
                    metrics.estimated_cost,
                    metrics.risk_max,
                    metrics.budget_violations_count,
                    metrics.budget_efficiency,
                    metrics.created_at,
                    json.dumps(metrics.metadata, ensure_ascii=False),
                ),
            )
        return metrics

    def get_run_metrics(self, run_id: str) -> dict | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM run_metrics WHERE run_id = ?", (run_id,)).fetchone()
        return _row_api(row) if row else None

    def aggregate_metrics(self, project_id: str | None = None, days: int = 7) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 7)))).isoformat()
        sql = """
            SELECT rm.*, r.status AS run_status, r.project_id
            FROM run_metrics rm
            JOIN runs r ON r.id = rm.run_id
            WHERE rm.created_at >= ?
        """
        params: list[object] = [cutoff]
        if project_id:
            sql += " AND r.project_id = ?"
            params.append(project_id)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            outcomes = conn.execute("SELECT * FROM task_outcomes WHERE created_at >= ?", (cutoff,)).fetchall()
        total = len(rows)
        succeeded = sum(1 for row in rows if row["run_status"] == "succeeded")
        tool_calls = sum(int(row["tool_calls_count"] or 0) for row in rows)
        failed_tools = sum(int(row["failed_tool_calls_count"] or 0) for row in rows)
        rollbacks = sum(int(row["rollbacks_count"] or 0) for row in rows)
        approvals = sum(int(row["approvals_count"] or 0) for row in rows)
        avg_duration = int(sum(int(row["total_duration_ms"] or 0) for row in rows) / total) if total else 0
        return redact(
            {
                "days": days,
                "runs": total,
                "task_success_rate": round(succeeded / total, 3) if total else 0,
                "average_duration_ms": avg_duration,
                "tool_failure_rate": round(failed_tools / tool_calls, 3) if tool_calls else 0,
                "rollback_rate": round(rollbacks / total, 3) if total else 0,
                "approval_friction": round(approvals / total, 3) if total else 0,
                "outcomes": _count_by(outcomes, "outcome"),
                "tool_calls": tool_calls,
                "failed_tool_calls": failed_tools,
                "rollbacks": rollbacks,
                "approvals": approvals,
                "budget_violations": sum(int(row["budget_violations_count"] or 0) for row in rows),
                "average_budget_efficiency": round(
                    sum(float(row["budget_efficiency"]) for row in rows if row["budget_efficiency"] is not None)
                    / max(1, sum(1 for row in rows if row["budget_efficiency"] is not None)),
                    3,
                ),
            }
        )

    def model_performance_summary(self) -> list[dict]:
        return self._group_summary("model_ref")

    def tool_reliability_summary(self) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT tool_name, status FROM action_journal WHERE tool_name IS NOT NULL").fetchall()
        grouped: dict[str, dict] = {}
        for row in rows:
            item = grouped.setdefault(row["tool_name"], {"tool_name": row["tool_name"], "calls": 0, "failures": 0, "denials": 0})
            item["calls"] += 1
            if row["status"] == "failed":
                item["failures"] += 1
            if row["status"] == "denied":
                item["denials"] += 1
        for item in grouped.values():
            item["success_rate"] = round((item["calls"] - item["failures"]) / item["calls"], 3) if item["calls"] else 0
        return sorted(grouped.values(), key=lambda item: (-item["calls"], item["tool_name"]))

    def agent_profile_performance_summary(self) -> list[dict]:
        return self._group_summary("agent_profile_id")

    def policy_friction_summary(self) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT tool_name, risk_level, status, policy_decision_json FROM action_journal WHERE status IN ('denied','approval_required')").fetchall()
        grouped: dict[str, dict] = {}
        for row in rows:
            key = str(row["tool_name"] or "unknown")
            item = grouped.setdefault(key, {"tool_name": key, "denied": 0, "approval_required": 0, "risk_levels": {}})
            item[row["status"]] += 1
            item["risk_levels"][row["risk_level"]] = item["risk_levels"].get(row["risk_level"], 0) + 1
        return sorted(grouped.values(), key=lambda item: (-(item["denied"] + item["approval_required"]), item["tool_name"]))

    def _group_summary(self, column: str) -> list[dict]:
        safe_column = "model_ref" if column == "model_ref" else "agent_profile_id"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                f"""
                SELECT COALESCE(rm.{safe_column}, 'unknown') AS key, COUNT(*) AS runs,
                       AVG(rm.total_duration_ms) AS avg_duration_ms,
                       SUM(CASE WHEN r.status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded,
                       SUM(rm.failed_tool_calls_count) AS failed_tool_calls
                FROM run_metrics rm
                JOIN runs r ON r.id = rm.run_id
                GROUP BY COALESCE(rm.{safe_column}, 'unknown')
                ORDER BY runs DESC
                """
            ).fetchall()
        return [
            {
                safe_column: row["key"],
                "runs": row["runs"],
                "success_rate": round((row["succeeded"] or 0) / row["runs"], 3) if row["runs"] else 0,
                "average_duration_ms": int(row["avg_duration_ms"] or 0),
                "failed_tool_calls": int(row["failed_tool_calls"] or 0),
            }
            for row in rows
        ]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _delta_ms(start: datetime, end: datetime | None) -> int:
    if end is None:
        return 0
    return int((end - start).total_seconds() * 1000)


def _event_matches_run(row, run_id: str) -> bool:
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return payload.get("run_id") == run_id


def _first_token_ms(events, run_id: str, started_at: datetime) -> int | None:
    for row in events:
        if not _event_matches_run(row, run_id):
            continue
        if row["type"] in {"reasoning.completed", "message.completed", "run.completed"}:
            created = _parse_dt(row["created_at"])
            return _delta_ms(started_at, created) if created else None
    return None


def _metadata_value(metadata_json: str | None, key: str):
    try:
        data = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        return None
    return data.get(key)


def _row_api(row) -> dict:
    item = dict(row)
    if item.get("metadata_json"):
        try:
            item["metadata"] = json.loads(item["metadata_json"])
        except json.JSONDecodeError:
            item["metadata"] = {}
    return redact(item)


def _count_by(rows, column: str) -> dict:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row[column] or "unknown")
        result[key] = result.get(key, 0) + 1
    return result
