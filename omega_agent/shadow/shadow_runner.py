from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.shadow.invariants import verify_invariants
from omega_agent.shadow.shadow_compare import compare_shadow_to_live as compare_files
from omega_agent.shadow.shadow_diff import collect_predicted_diff as build_predicted_diff
from omega_agent.shadow.shadow_plan import build_plan
from omega_agent.shadow.shadow_risk import compute_risk_report as build_risk_report
from omega_agent.shadow.shadow_workspace import ShadowWorkspace
from omega_agent.workflows.workflow_store import WorkflowStore

if TYPE_CHECKING:
    from omega_agent.runtime.durable_runtime import DurableRuntime
    from omega_agent.runtime.sessions import SessionsStore
    from omega_agent.runtime.tool_broker import ToolBroker


class ShadowRunner:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self._broker: ToolBroker | None = None
        self._durable: DurableRuntime | None = None
        self._sessions: SessionsStore | None = None
        with connect_runtime_db(config):
            pass

    @property
    def broker(self) -> ToolBroker:
        if self._broker is None:
            from omega_agent.runtime.tool_broker import ToolBroker

            self._broker = ToolBroker(self.config)
        return self._broker

    @property
    def durable(self) -> DurableRuntime:
        if self._durable is None:
            from omega_agent.runtime.durable_runtime import DurableRuntime

            self._durable = DurableRuntime(self.config)
        return self._durable

    @property
    def sessions(self) -> SessionsStore:
        if self._sessions is None:
            from omega_agent.runtime.sessions import SessionsStore

            self._sessions = SessionsStore(self.config)
        return self._sessions

    def create_shadow_run(
        self,
        objective: str,
        source_type: str = "manual_plan",
        source_id: str | None = None,
        *,
        plan: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.shadow_enabled:
            raise ValueError("Shadow execution disabled by configuration.")
        self.expire_old_shadow_runs()
        if source_type not in {"action", "run", "workflow", "manual_plan"}:
            raise ValueError("source_type shadow invalide.")
        workflow_definition = None
        if source_type == "workflow":
            workflow = WorkflowStore(self.config).get_workflow(str(source_id or ""))
            if workflow is None:
                raise ValueError("Workflow source introuvable.")
            workflow_definition = workflow.definition
            objective = objective or f"Workflow: {workflow.name}"
        compiled = redact(plan or build_plan(objective, source_type=source_type, workflow_definition=workflow_definition))
        shadow_run_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO shadow_runs(
                    id, source_type, source_id, status, objective, plan_json,
                    risk_report_json, predicted_diff_json, estimated_cost_json,
                    created_at, completed_at, metadata_json
                )
                VALUES (?, ?, ?, 'pending', ?, ?, NULL, NULL, NULL, ?, NULL, ?)
                """,
                (
                    shadow_run_id,
                    source_type,
                    source_id,
                    redact(objective),
                    json.dumps(compiled, ensure_ascii=False),
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        self.events.add("shadow.created", {"shadow_run_id": shadow_run_id, "source_type": source_type, "source_id": source_id})
        return self.get_shadow_run(shadow_run_id)

    def build_shadow_plan(self, objective: str) -> dict[str, Any]:
        return build_plan(objective)

    def run_shadow(self, shadow_run_id: str) -> dict[str, Any]:
        shadow_run = self.require_shadow_run(shadow_run_id)
        if shadow_run["status"] in {"promoted", "rejected", "expired"}:
            raise ValueError(f"Shadow run non exécutable: {shadow_run['status']}.")
        plan = shadow_run["plan"]
        workspace = ShadowWorkspace(self.config, shadow_run_id)
        workspace.prepare(plan)
        with connect_runtime_db(self.config) as conn:
            conn.execute("DELETE FROM shadow_steps WHERE shadow_run_id = ?", (shadow_run_id,))
        self._update_run(shadow_run_id, status="running", completed_at=None)
        self.events.add("shadow.started", {"shadow_run_id": shadow_run_id})
        step_results: list[dict[str, Any]] = []
        started_at = datetime.now(timezone.utc)
        try:
            for index, planned in enumerate(plan.get("steps") or []):
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                if elapsed > max(1, int(self.config.shadow_max_shadow_seconds)):
                    raise TimeoutError("Shadow run timed out.")
                step_id = self._create_step(shadow_run_id, index, planned)
                self.events.add("shadow.step.started", {"shadow_run_id": shadow_run_id, "shadow_step_id": step_id, "step_index": index})
                result = self._execute_planned_step(shadow_run_id, planned, workspace)
                step_results.append(result)
                self._complete_step(step_id, result)
                self.events.add(
                    "shadow.step.completed",
                    {"shadow_run_id": shadow_run_id, "shadow_step_id": step_id, "step_index": index, "status": result["status"]},
                )
                if result["status"] == "failed":
                    raise RuntimeError(str(result.get("error") or result.get("output") or "Shadow step failed."))
            predicted_diff = self.collect_predicted_diff(shadow_run_id)
            invariants = verify_invariants(self.config, shadow_run_id, plan, step_results)
            risk_report = build_risk_report(self.config, plan, predicted_diff, step_results, invariants)
            estimated_cost = {
                "duration_seconds": round((datetime.now(timezone.utc) - started_at).total_seconds(), 3),
                "tool_calls": sum(1 for step in plan.get("steps") or [] if step.get("tool_name")),
                "estimated_tokens": 0,
                "estimated_cost": 0.0,
                "simulation": True,
            }
            status = "succeeded" if invariants.get("passed") else "failed"
            self._update_run(
                shadow_run_id,
                status=status,
                risk_report=risk_report,
                predicted_diff=predicted_diff,
                estimated_cost=estimated_cost,
                completed_at=_now(),
            )
            if status == "failed":
                self.events.add("shadow.failed", {"shadow_run_id": shadow_run_id, "reason": "invariant_failed"})
            return self.get_shadow_run(shadow_run_id)
        except Exception as exc:
            predicted_diff = self.collect_predicted_diff(shadow_run_id)
            invariants = verify_invariants(self.config, shadow_run_id, plan, step_results)
            risk_report = build_risk_report(self.config, plan, predicted_diff, step_results, invariants)
            risk_report["recommendation"] = "reject"
            risk_report["error"] = redact(str(exc))
            self._update_run(
                shadow_run_id,
                status="failed",
                risk_report=risk_report,
                predicted_diff=predicted_diff,
                completed_at=_now(),
                metadata={**shadow_run.get("metadata", {}), "error": redact(str(exc))},
            )
            self.events.add("shadow.failed", {"shadow_run_id": shadow_run_id, "reason": redact(str(exc))})
            return self.get_shadow_run(shadow_run_id)

    def collect_predicted_diff(self, shadow_run_id: str) -> dict[str, Any]:
        shadow_run = self.require_shadow_run(shadow_run_id)
        diff = build_predicted_diff(self.config, shadow_run_id, shadow_run["plan"])
        self._update_run(shadow_run_id, predicted_diff=diff)
        self.events.add("shadow.diff.created", {"shadow_run_id": shadow_run_id, "summary": diff.get("summary")})
        return diff

    def compute_risk_report(self, shadow_run_id: str) -> dict[str, Any]:
        shadow_run = self.require_shadow_run(shadow_run_id)
        steps = self.list_steps(shadow_run_id)
        diff = shadow_run.get("predicted_diff") or self.collect_predicted_diff(shadow_run_id)
        invariants = verify_invariants(self.config, shadow_run_id, shadow_run["plan"], steps)
        report = build_risk_report(self.config, shadow_run["plan"], diff, steps, invariants)
        self._update_run(shadow_run_id, risk_report=report)
        self.events.add("shadow.risk.created", {"shadow_run_id": shadow_run_id, "recommendation": report.get("recommendation")})
        return report

    def promote_to_live(self, shadow_run_id: str, approved_by: str | None = None) -> dict[str, Any]:
        shadow_run = self.require_shadow_run(shadow_run_id)
        if shadow_run["status"] != "succeeded":
            raise ValueError("Un shadow run doit réussir avant promotion.")
        risk = shadow_run.get("risk_report") or self.compute_risk_report(shadow_run_id)
        if risk.get("recommendation") == "reject":
            raise PermissionError("Promotion refusée par le rapport de risque.")
        approval_required = risk.get("recommendation") == "require_approval" or risk.get("risk_level") in {"high", "critical"} or bool(risk.get("external_calls"))
        promotion = self._latest_promotion(shadow_run_id)
        if promotion is None:
            promotion_id = uuid4().hex
            now = _now()
            with connect_runtime_db(self.config) as conn:
                conn.execute(
                    """
                    INSERT INTO shadow_promotions(
                        id, shadow_run_id, live_run_id, status, approved_by,
                        approved_at, created_at, completed_at, metadata_json
                    )
                    VALUES (?, ?, NULL, 'pending', NULL, NULL, ?, NULL, '{}')
                    """,
                    (promotion_id, shadow_run_id, now),
                )
            promotion = self._get_promotion(promotion_id)
        if approval_required and not approved_by:
            return {"shadow_run": self.get_shadow_run(shadow_run_id), "promotion": promotion, "approval_required": True}
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE shadow_promotions SET status = 'approved', approved_by = ?, approved_at = ? WHERE id = ?",
                (redact(approved_by or "policy"), now, promotion["id"]),
            )
        session_id = self.sessions.default_session_id()
        live = self.durable.create_run(
            session_id,
            shadow_run["objective"],
            metadata={"source": "shadow_promotion", "shadow_run_id": shadow_run_id, "shadow_promotion_id": promotion["id"]},
        )
        self.durable.start_run(live.id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE shadow_promotions SET status = 'running', live_run_id = ? WHERE id = ?",
                (live.id, promotion["id"]),
            )
        outputs: list[dict[str, Any]] = []
        try:
            for step in shadow_run["plan"].get("steps") or []:
                tool_name = step.get("tool_name")
                if not tool_name:
                    continue
                result = self.broker.call(
                    str(tool_name),
                    dict(step.get("arguments") or {}),
                    session_id=session_id,
                    run_id=live.id,
                    shadow_run_id=shadow_run_id,
                )
                outputs.append({"tool_name": tool_name, "status": result.status, "output": redact(result.output)})
                if result.status == "approval_required":
                    with connect_runtime_db(self.config) as conn:
                        conn.execute(
                            "UPDATE shadow_promotions SET status = 'approved', metadata_json = ? WHERE id = ?",
                            (json.dumps(redact({"live_approval_required": True, "outputs": outputs}), ensure_ascii=False), promotion["id"]),
                        )
                    return {"shadow_run": self.get_shadow_run(shadow_run_id), "promotion": self._get_promotion(promotion["id"]), "live_run": self.durable.get_run(live.id).as_api()}
                if result.status not in {"completed"}:
                    raise RuntimeError(result.output)
            self.durable.complete_run(live.id, "Shadow plan promoted and executed live.")
            comparison = self.compare_shadow_to_live(shadow_run_id, live.id) if self.config.shadow_compare_after_live else None
            with connect_runtime_db(self.config) as conn:
                conn.execute(
                    "UPDATE shadow_promotions SET status = 'succeeded', completed_at = ?, metadata_json = ? WHERE id = ?",
                    (_now(), json.dumps(redact({"outputs": outputs}), ensure_ascii=False), promotion["id"]),
                )
                conn.execute("UPDATE shadow_runs SET status = 'promoted' WHERE id = ?", (shadow_run_id,))
            self.events.add("shadow.promoted", {"shadow_run_id": shadow_run_id, "live_run_id": live.id})
            return {
                "shadow_run": self.get_shadow_run(shadow_run_id),
                "promotion": self._get_promotion(promotion["id"]),
                "live_run": self.durable.get_run(live.id).as_api(),
                "comparison": comparison,
            }
        except Exception as exc:
            self.durable.fail_run(live.id, str(exc))
            with connect_runtime_db(self.config) as conn:
                conn.execute(
                    "UPDATE shadow_promotions SET status = 'failed', completed_at = ?, metadata_json = ? WHERE id = ?",
                    (_now(), json.dumps(redact({"error": str(exc), "outputs": outputs}), ensure_ascii=False), promotion["id"]),
                )
            raise

    def compare_shadow_to_live(self, shadow_run_id: str, live_run_id: str) -> dict[str, Any]:
        shadow_run = self.require_shadow_run(shadow_run_id)
        if self.durable.get_run(live_run_id) is None:
            raise ValueError("Live run introuvable.")
        comparison = compare_files(self.config, shadow_run_id, shadow_run.get("predicted_diff") or {})
        comparison_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO shadow_live_comparisons(
                    id, shadow_run_id, live_run_id, comparison_json,
                    success_match, diff_match_score, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
                """,
                (
                    comparison_id,
                    shadow_run_id,
                    live_run_id,
                    json.dumps(redact(comparison), ensure_ascii=False),
                    int(bool(comparison.get("success_match"))),
                    float(comparison.get("diff_match_score") or 0),
                    _now(),
                ),
            )
        self.events.add("shadow.comparison.created", {"shadow_run_id": shadow_run_id, "live_run_id": live_run_id, "diff_match_score": comparison.get("diff_match_score")})
        return {"id": comparison_id, "shadow_run_id": shadow_run_id, "live_run_id": live_run_id, **comparison}

    def reject(self, shadow_run_id: str) -> dict[str, Any]:
        self.require_shadow_run(shadow_run_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE shadow_runs SET status = 'rejected', completed_at = COALESCE(completed_at, ?) WHERE id = ?", (_now(), shadow_run_id))
            promotion = self._latest_promotion(shadow_run_id)
            if promotion:
                conn.execute("UPDATE shadow_promotions SET status = 'rejected', completed_at = ? WHERE id = ?", (_now(), promotion["id"]))
        self.events.add("shadow.rejected", {"shadow_run_id": shadow_run_id})
        return self.get_shadow_run(shadow_run_id)

    def expire_old_shadow_runs(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, int(self.config.shadow_workspace_keep_days)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT id FROM shadow_runs WHERE status NOT IN ('promoted','expired') AND created_at < ?",
                (cutoff.isoformat(),),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                conn.executemany("UPDATE shadow_runs SET status = 'expired', completed_at = COALESCE(completed_at, ?) WHERE id = ?", [(_now(), item) for item in ids])
        ShadowWorkspace.expire_old(self.config)
        return ids

    def list_shadow_runs(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM shadow_runs"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._run_from_row(row, include_related=False) for row in rows]

    def get_shadow_run(self, shadow_run_id: str) -> dict[str, Any] | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM shadow_runs WHERE id = ?", (shadow_run_id,)).fetchone()
        return self._run_from_row(row, include_related=True) if row else None

    def require_shadow_run(self, shadow_run_id: str) -> dict[str, Any]:
        item = self.get_shadow_run(shadow_run_id)
        if item is None:
            raise ValueError("Shadow run introuvable.")
        return item

    def list_steps(self, shadow_run_id: str) -> list[dict[str, Any]]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM shadow_steps WHERE shadow_run_id = ? ORDER BY step_index ASC", (shadow_run_id,)).fetchall()
        return [_step_from_row(row) for row in rows]

    def get_comparison(self, shadow_run_id: str) -> dict[str, Any] | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM shadow_live_comparisons WHERE shadow_run_id = ? ORDER BY created_at DESC LIMIT 1",
                (shadow_run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "shadow_run_id": row["shadow_run_id"],
            "live_run_id": row["live_run_id"],
            "comparison": _json(row["comparison_json"], {}),
            "success_match": None if row["success_match"] is None else bool(row["success_match"]),
            "diff_match_score": row["diff_match_score"],
            "created_at": row["created_at"],
            "metadata": _json(row["metadata_json"], {}),
        }

    def _execute_planned_step(self, shadow_run_id: str, planned: dict[str, Any], workspace: ShadowWorkspace) -> dict[str, Any]:
        if not planned.get("simulable", True):
            return {
                "status": "skipped",
                "output": "Action non simulable.",
                "simulated": True,
                "action_category": planned.get("action_category"),
                "risk_level": planned.get("risk_level"),
            }
        tool_name = planned.get("tool_name")
        if not tool_name:
            return {
                "status": "succeeded",
                "output": "Étape logique simulée.",
                "simulated": True,
                "action_category": planned.get("action_category"),
                "risk_level": planned.get("risk_level"),
            }
        result = self.broker.call(
            str(tool_name),
            dict(planned.get("arguments") or {}),
            execution_mode="shadow",
            shadow_workspace=workspace.workspace,
            shadow_run_id=shadow_run_id,
        )
        metadata = dict(result.metadata or {})
        return {
            "status": "skipped" if result.status == "shadow_skipped" else "succeeded" if result.status == "completed" else "failed",
            "output": redact(result.output),
            "error": redact(result.output) if result.status not in {"completed", "shadow_skipped"} else None,
            "simulated": True,
            "policy_denied": result.status == "denied",
            "action_category": planned.get("action_category"),
            "risk_level": planned.get("risk_level"),
            "metadata": metadata,
        }

    def _create_step(self, shadow_run_id: str, index: int, planned: dict[str, Any]) -> str:
        step_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO shadow_steps(
                    id, shadow_run_id, step_index, name, type, status,
                    input_json, output_json, error, created_at, completed_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, 'running', ?, NULL, NULL, ?, NULL, ?)
                """,
                (
                    step_id,
                    shadow_run_id,
                    index,
                    str(planned.get("name") or f"Step {index + 1}"),
                    str(planned.get("type") or "tool"),
                    json.dumps(redact(planned.get("arguments") or {}), ensure_ascii=False),
                    _now(),
                    json.dumps(redact({"planned": planned, "simulation": True}), ensure_ascii=False),
                ),
            )
        return step_id

    def _complete_step(self, step_id: str, result: dict[str, Any]) -> None:
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE shadow_steps SET status = ?, output_json = ?, error = ?, completed_at = ?, metadata_json = ? WHERE id = ?",
                (
                    result["status"],
                    json.dumps(redact(result), ensure_ascii=False),
                    redact(result.get("error")),
                    _now(),
                    json.dumps(redact({"simulation": True, **(result.get("metadata") or {})}), ensure_ascii=False),
                    step_id,
                ),
            )

    def _update_run(
        self,
        shadow_run_id: str,
        *,
        status: str | None = None,
        risk_report: dict[str, Any] | None = None,
        predicted_diff: dict[str, Any] | None = None,
        estimated_cost: dict[str, Any] | None = None,
        completed_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        fields: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("status", status),
            ("risk_report_json", json.dumps(redact(risk_report), ensure_ascii=False) if risk_report is not None else None),
            ("predicted_diff_json", json.dumps(redact(predicted_diff), ensure_ascii=False) if predicted_diff is not None else None),
            ("estimated_cost_json", json.dumps(redact(estimated_cost), ensure_ascii=False) if estimated_cost is not None else None),
            ("completed_at", completed_at),
            ("metadata_json", json.dumps(redact(metadata), ensure_ascii=False) if metadata is not None else None),
        ):
            if value is not None or column == "completed_at" and completed_at is not None:
                fields.append(f"{column} = ?")
                params.append(value)
        if not fields:
            return
        params.append(shadow_run_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE shadow_runs SET {', '.join(fields)} WHERE id = ?", tuple(params))

    def _run_from_row(self, row, *, include_related: bool) -> dict[str, Any]:
        item = {
            "id": row["id"],
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "status": row["status"],
            "objective": row["objective"],
            "plan": _json(row["plan_json"], {}),
            "risk_report": _json(row["risk_report_json"], None),
            "predicted_diff": _json(row["predicted_diff_json"], None),
            "estimated_cost": _json(row["estimated_cost_json"], None),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "metadata": _json(row["metadata_json"], {}),
        }
        if include_related:
            item["steps"] = self.list_steps(row["id"])
            item["promotion"] = self._latest_promotion(row["id"])
            item["comparison"] = self.get_comparison(row["id"])
        return redact(item)

    def _latest_promotion(self, shadow_run_id: str) -> dict[str, Any] | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM shadow_promotions WHERE shadow_run_id = ? ORDER BY created_at DESC LIMIT 1",
                (shadow_run_id,),
            ).fetchone()
        return _promotion_from_row(row) if row else None

    def _get_promotion(self, promotion_id: str) -> dict[str, Any] | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM shadow_promotions WHERE id = ?", (promotion_id,)).fetchone()
        return _promotion_from_row(row) if row else None


def _step_from_row(row) -> dict[str, Any]:
    output = _json(row["output_json"], None)
    result = {
        "id": row["id"],
        "shadow_run_id": row["shadow_run_id"],
        "step_index": int(row["step_index"]),
        "name": row["name"],
        "type": row["type"],
        "status": row["status"],
        "input": _json(row["input_json"], None),
        "output": output,
        "error": row["error"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "metadata": _json(row["metadata_json"], {}),
    }
    if isinstance(output, dict):
        for key in ("simulated", "policy_denied", "action_category", "risk_level"):
            if key in output:
                result[key] = output[key]
    return redact(result)


def _promotion_from_row(row) -> dict[str, Any]:
    return redact(
        {
            "id": row["id"],
            "shadow_run_id": row["shadow_run_id"],
            "live_run_id": row["live_run_id"],
            "status": row["status"],
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "metadata": _json(row["metadata_json"], {}),
        }
    )


def _json(value: str | None, fallback):
    try:
        return json.loads(value) if value is not None else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
