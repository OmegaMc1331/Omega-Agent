from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.evals.metrics import MetricsStore
from omega_agent.evals.task_outcomes import TaskOutcomesStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class RunScoring:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.metrics = MetricsStore(config)
        self.outcomes = TaskOutcomesStore(config)

    def score_run(self, run_id: str) -> dict:
        metrics = self.metrics.compute_run_metrics(run_id)
        task = self.score_task_completion(run_id)
        tool = self.score_tool_reliability(run_id)
        rollback = self.score_rollback_rate(run_id)
        friction = self.score_policy_friction(run_id)
        intervention = self.score_user_intervention(run_id)
        final_response = self._score_final_response(run_id)
        duration = 10 if metrics.total_duration_ms <= int(self.config.runtime_max_run_seconds) * 1000 else 0
        budget_penalty = min(20, metrics.budget_violations_count * 10)
        score = max(0, min(100, task + tool + rollback + duration + friction + final_response - budget_penalty))
        outcome = "success" if score >= 70 and task else "partial" if score >= 40 else "failed"
        stored = self.outcomes.record_auto_outcome(
            run_id,
            auto_score=float(score),
            outcome=outcome,
            reason="Auto scoring Omega Evaluation Loop v1",
            metadata={
                "task_completion": task,
                "tool_reliability": tool,
                "rollback": rollback,
                "duration": duration,
                "policy_friction": friction,
                "final_response": final_response,
                "user_intervention": intervention,
                "budget_violations": metrics.budget_violations_count,
                "budget_efficiency": metrics.budget_efficiency,
                "budget_penalty": budget_penalty,
            },
        )
        return redact({"run_id": run_id, "score": score, "outcome": stored.as_api(), "metrics": metrics.as_api()})

    def score_task_completion(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            run = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("Run introuvable.")
        return 40 if run["status"] == "succeeded" else 0

    def score_tool_reliability(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            failed = conn.execute("SELECT COUNT(*) AS c FROM action_journal WHERE run_id = ? AND status = 'failed'", (run_id,)).fetchone()["c"]
        return 20 if int(failed or 0) == 0 else 0

    def score_policy_friction(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            denied = conn.execute("SELECT COUNT(*) AS c FROM action_journal WHERE run_id = ? AND status = 'denied'", (run_id,)).fetchone()["c"]
        return 10 if int(denied or 0) == 0 else 0

    def score_rollback_rate(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            failed_rollbacks = conn.execute("SELECT COUNT(*) AS c FROM rollback_events WHERE run_id = ? AND status = 'failed'", (run_id,)).fetchone()["c"]
        return 10 if int(failed_rollbacks or 0) == 0 else 0

    def score_user_intervention(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            approvals = conn.execute("SELECT COUNT(*) AS c FROM action_journal WHERE run_id = ? AND status = 'approval_required'", (run_id,)).fetchone()["c"]
        return 10 if int(approvals or 0) == 0 else 0

    def _score_final_response(self, run_id: str) -> int:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT output_json FROM run_steps WHERE run_id = ? AND type = 'final_response' AND status = 'succeeded' ORDER BY completed_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        return 10 if row and row["output_json"] else 0
