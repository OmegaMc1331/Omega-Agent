from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.evals.datasets import load_eval_dataset
from omega_agent.evals.run_scoring import RunScoring
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.sandbox import safe_path
from omega_agent.security.redaction import redact


class EvalRunner:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def load_eval_dataset(self, path_or_name: str) -> dict:
        return load_eval_dataset(self.config, path_or_name)

    async def run_eval_dataset(self, dataset_name: str) -> dict:
        dataset = self.load_eval_dataset(dataset_name)
        eval_run_id = self._create_eval_run(dataset["name"], dataset.get("description", ""), dataset_name)
        summary = {"total": 0, "passed": 0, "failed": 0, "error": 0, "scores": []}
        self._update_eval_run(eval_run_id, status="running", started_at=_now())
        for case in dataset["cases"]:
            summary["total"] += 1
            try:
                result = await self.run_eval_case(case, eval_run_id=eval_run_id)
                summary[result["status"]] = summary.get(result["status"], 0) + 1
                if result.get("score") is not None:
                    summary["scores"].append(result["score"])
            except Exception as exc:
                summary["error"] += 1
                self._store_case(eval_run_id, case, status="error", error=str(exc))
        average = round(sum(summary["scores"]) / len(summary["scores"]), 2) if summary["scores"] else 0
        summary["average_score"] = average
        final_status = "succeeded" if summary["failed"] == 0 and summary["error"] == 0 else "failed"
        self._update_eval_run(eval_run_id, status=final_status, completed_at=_now(), summary=summary)
        return self.get_eval_run(eval_run_id)

    async def run_eval_case(self, case: dict, *, eval_run_id: str | None = None) -> dict:
        eval_run_id = eval_run_id or self._create_eval_run("single-case", "", None)
        case_id = self._store_case(eval_run_id, case, status="running", started_at=_now())
        self._apply_project_setup(case)
        session = SessionsStore(self.config).create_session(f"Eval: {case.get('name') or 'case'}")
        runtime = OmegaRuntime(self.config)
        output = await runtime.send_message(str(case["prompt"]), session_id=session.id)
        run_id = runtime.last_run_id
        if not run_id:
            raise RuntimeError("Eval case sans run_id.")
        comparison = self.compare_expected_outcome(case, run_id, output)
        score_payload = RunScoring(self.config).score_run(run_id)
        score = 100.0 if comparison["passed"] else min(float(score_payload["score"]), 60.0)
        status = "passed" if comparison["passed"] else "failed"
        result = {
            "run_id": run_id,
            "session_id": session.id,
            "output": output,
            "comparison": comparison,
            "score": score,
            "auto_score": score_payload,
        }
        self.store_eval_result(case_id, result, status=status, score=score)
        return {"case_id": case_id, "run_id": run_id, "status": status, "score": score, "result": redact(result)}

    def compare_expected_outcome(self, case: dict, run_id: str, output: str = "") -> dict:
        checks: list[dict] = []
        with connect_runtime_db(self.config) as conn:
            actions = conn.execute("SELECT * FROM action_journal WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        action_tools = [row["tool_name"] for row in actions]
        denied = any(row["status"] == "denied" for row in actions)
        for relative_path in case.get("expected_files_created") or []:
            path = safe_path(self.config, relative_path)
            checks.append({"kind": "file_created", "target": relative_path, "passed": path.exists()})
        for relative_path in case.get("expected_files_modified") or []:
            path = safe_path(self.config, relative_path)
            checks.append({"kind": "file_modified", "target": relative_path, "passed": path.exists()})
        expected_contains = case.get("expected_contains")
        if isinstance(expected_contains, dict):
            for relative_path, expected in expected_contains.items():
                path = safe_path(self.config, str(relative_path))
                text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
                checks.append({"kind": "contains", "target": relative_path, "passed": str(expected) in text})
        elif isinstance(expected_contains, str) and expected_contains:
            checks.append({"kind": "output_contains", "target": "assistant", "passed": expected_contains in output})
        if case.get("expected_denied"):
            checks.append({"kind": "expected_denied", "target": "policy", "passed": denied})
        for tool in case.get("expected_tool_calls") or []:
            checks.append({"kind": "tool_call", "target": tool, "passed": tool in action_tools})
        passed = all(item["passed"] for item in checks) if checks else True
        return redact({"passed": passed, "checks": checks, "actions": action_tools, "denied": denied})

    def store_eval_result(self, case_id: str, result: dict, *, status: str, score: float | None = None, error: str | None = None) -> None:
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE eval_cases SET status = ?, score = ?, completed_at = ?, result_json = ?, error = ? WHERE id = ?",
                (status, score, _now(), json.dumps(redact(result), ensure_ascii=False), redact(error), case_id),
            )

    def list_eval_runs(self, limit: int = 100) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [_row_api(row) for row in rows]

    def get_eval_run(self, eval_run_id: str) -> dict:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (eval_run_id,)).fetchone()
        if row is None:
            raise ValueError("Eval run introuvable.")
        return _row_api(row)

    def list_cases(self, eval_run_id: str) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM eval_cases WHERE eval_run_id = ? ORDER BY started_at ASC, name ASC", (eval_run_id,)).fetchall()
        return [_row_api(row) for row in rows]

    def cancel_eval_run(self, eval_run_id: str) -> dict:
        self._update_eval_run(eval_run_id, status="cancelled", completed_at=_now())
        return self.get_eval_run(eval_run_id)

    def _apply_project_setup(self, case: dict) -> None:
        setup = case.get("project_setup") if isinstance(case.get("project_setup"), dict) else {}
        files = setup.get("files") if isinstance(setup.get("files"), dict) else {}
        for relative_path, content in files.items():
            path = safe_path(self.config, str(relative_path))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")

    def _create_eval_run(self, name: str, description: str, dataset_name: str | None) -> str:
        eval_run_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO eval_runs(id, name, description, status, dataset_name, created_at, metadata_json) VALUES (?, ?, ?, 'pending', ?, ?, '{}')",
                (eval_run_id, redact(name), redact(description), redact(dataset_name), now),
            )
        return eval_run_id

    def _update_eval_run(self, eval_run_id: str, *, status: str | None = None, started_at: str | None = None, completed_at: str | None = None, summary: dict | None = None) -> None:
        updates = []
        params: list[object] = []
        if status:
            updates.append("status = ?")
            params.append(status)
        if started_at:
            updates.append("started_at = ?")
            params.append(started_at)
        if completed_at:
            updates.append("completed_at = ?")
            params.append(completed_at)
        if summary is not None:
            updates.append("summary_json = ?")
            params.append(json.dumps(redact(summary), ensure_ascii=False))
        if not updates:
            return
        params.append(eval_run_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(f"UPDATE eval_runs SET {', '.join(updates)} WHERE id = ?", tuple(params))

    def _store_case(self, eval_run_id: str, case: dict, *, status: str, started_at: str | None = None, error: str | None = None) -> str:
        case_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO eval_cases(
                    id, eval_run_id, name, prompt, expected_outcome, project_id,
                    agent_profile_id, model_ref, status, started_at, error, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    eval_run_id,
                    redact(str(case.get("name") or "")),
                    redact(str(case.get("prompt") or "")),
                    json.dumps(redact(case), ensure_ascii=False),
                    case.get("project_id"),
                    case.get("agent_profile_id"),
                    case.get("model_ref"),
                    status,
                    started_at,
                    redact(error),
                    json.dumps(redact(case.get("metadata") or {}), ensure_ascii=False),
                ),
            )
        return case_id


def run_eval_dataset_sync(config: OmegaConfig, dataset_name: str) -> dict:
    return asyncio.run(EvalRunner(config).run_eval_dataset(dataset_name))


def _row_api(row) -> dict:
    item = dict(row)
    for key in ("summary_json", "result_json", "metadata_json", "expected_outcome"):
        if item.get(key):
            try:
                item[key[:-5] if key.endswith("_json") else key] = json.loads(item[key])
            except json.JSONDecodeError:
                pass
    return redact(item)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
