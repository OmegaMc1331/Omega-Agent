from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.repo_analyzer import RepoSummary
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.test_runner import CodeTestRunner
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.security import safe_path
from omega_agent.security.redaction import redact
from omega_agent.tools.git import git_diff


@dataclass(frozen=True)
class PatchPlan:
    id: str
    run_id: str | None
    project_id: str | None
    title: str
    problem: str
    proposed_changes: list[dict]
    proposed_changes_json: str
    files_to_modify: list[str]
    files_to_modify_json: str
    risk_level: str
    status: str
    created_at: str
    updated_at: str
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


def create_patch_plan(error_summary: str, repo_summary: RepoSummary | dict, proposed_changes: list[dict] | None = None) -> dict:
    files = _files_from_changes(proposed_changes or [])
    languages = repo_summary.languages if isinstance(repo_summary, RepoSummary) else repo_summary.get("languages", [])
    return {
        "title": "Correction minimale proposee",
        "problem": str(error_summary or "Erreur a analyser.")[:2000],
        "proposed_changes": proposed_changes or [],
        "files_to_modify": files,
        "risk_level": "medium" if files else "low",
        "metadata": {"languages": languages},
    }


class PatchPlanner:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def create_patch_plan(
        self,
        error_summary: str,
        repo_summary: RepoSummary | dict,
        proposed_changes: list[dict] | None = None,
        *,
        run_id: str | None = None,
        project_id: str | None = None,
        title: str | None = None,
    ) -> PatchPlan:
        plan_data = create_patch_plan(error_summary, repo_summary, proposed_changes)
        if title:
            plan_data["title"] = title
        return self.store_plan(plan_data, run_id=run_id, project_id=project_id)

    def store_plan(self, plan_data: dict, *, run_id: str | None = None, project_id: str | None = None) -> PatchPlan:
        now = _now()
        proposed_changes = list(plan_data.get("proposed_changes") or [])
        files_to_modify = list(plan_data.get("files_to_modify") or _files_from_changes(proposed_changes))
        proposed_json = json.dumps(redact(proposed_changes), ensure_ascii=False)
        files_json = json.dumps(files_to_modify, ensure_ascii=False)
        metadata_json = json.dumps(redact(plan_data.get("metadata") or {}), ensure_ascii=False)
        plan = PatchPlan(
            id=uuid4().hex,
            run_id=run_id,
            project_id=project_id,
            title=str(plan_data.get("title") or "Patch plan")[:200],
            problem=str(plan_data.get("problem") or "")[:4000],
            proposed_changes=proposed_changes,
            proposed_changes_json=proposed_json,
            files_to_modify=files_to_modify,
            files_to_modify_json=files_json,
            risk_level=str(plan_data.get("risk_level") or "medium"),
            status="proposed",
            created_at=now,
            updated_at=now,
            metadata=json.loads(metadata_json),
            metadata_json=metadata_json,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO patch_plans(
                    id, run_id, project_id, title, problem, proposed_changes_json, files_to_modify_json,
                    risk_level, status, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.id,
                    plan.run_id,
                    plan.project_id,
                    plan.title,
                    plan.problem,
                    plan.proposed_changes_json,
                    plan.files_to_modify_json,
                    plan.risk_level,
                    plan.status,
                    plan.created_at,
                    plan.updated_at,
                    plan.metadata_json,
                ),
            )
        self.events.add("patch.plan.created", {"patch_plan_id": plan.id, "run_id": run_id, "project_id": project_id})
        return plan

    def apply_patch_plan(self, plan_id: str, *, session_id: str | None = None) -> PatchPlan | None:
        plan = self.get(plan_id)
        if plan is None:
            return None
        broker = ToolBroker(self.config)
        outputs = []
        try:
            for change in plan.proposed_changes:
                relative_path = str(change.get("relative_path") or change.get("path") or "").strip()
                if not relative_path:
                    continue
                safe_path(self.config, relative_path)
                content = _content_for_change(self.config, change)
                result = broker.call("write_file", {"relative_path": relative_path, "content": content}, session_id=session_id, run_id=plan.run_id)
                outputs.append(result.output)
                if result.status not in {"completed"}:
                    raise RuntimeError(result.output)
            updated = self._set_status(plan.id, "applied", {"apply_outputs": outputs})
            self.events.add("patch.applied", {"patch_plan_id": plan.id, "files": plan.files_to_modify})
            return updated
        except Exception as exc:
            self._set_status(plan.id, "failed", {"error": str(exc), "apply_outputs": outputs})
            return self.get(plan.id)

    def verify_patch(self, plan_id: str) -> PatchPlan | None:
        plan = self.get(plan_id)
        if plan is None:
            return None
        result = CodeTestRunner(self.config).run_detected_tests(project_id=plan.project_id, run_id=plan.run_id)
        status = "verified" if result.status == "passed" else "failed"
        updated = self._set_status(plan.id, status, {"test_run_id": result.id, "test_status": result.status, "summary": result.summary})
        event = "patch.verified" if status == "verified" else "patch.failed"
        self.events.add(event, {"patch_plan_id": plan.id, "test_run_id": result.id, "status": status})
        return updated

    def produce_diff_summary(self) -> dict:
        diff = git_diff(self.config)
        files = []
        added = 0
        removed = 0
        for line in diff.splitlines():
            if line.startswith("diff --git "):
                parts = line.split(" b/")
                if len(parts) == 2:
                    files.append(parts[1])
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        self.events.add("git.diff.updated", {"files": files, "added": added, "removed": removed})
        return {"diff": diff, "files": files, "added": added, "removed": removed}

    def list_plans(self, project_id: str | None = None, limit: int = 100) -> list[PatchPlan]:
        sql = "SELECT * FROM patch_plans"
        params: list[object] = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_from_row(row) for row in rows]

    def get(self, plan_id: str) -> PatchPlan | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM patch_plans WHERE id = ?", (plan_id,)).fetchone()
        return _from_row(row) if row else None

    def _set_status(self, plan_id: str, status: str, metadata_update: dict | None = None) -> PatchPlan | None:
        current = self.get(plan_id)
        if current is None:
            return None
        metadata = dict(current.metadata)
        metadata.update(redact(metadata_update or {}))
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE patch_plans SET status = ?, updated_at = ?, metadata_json = ? WHERE id = ?",
                (status, _now(), json.dumps(metadata, ensure_ascii=False), plan_id),
            )
        return self.get(plan_id)


def apply_patch_plan(plan: PatchPlan, config: OmegaConfig) -> PatchPlan | None:
    return PatchPlanner(config).apply_patch_plan(plan.id)


def verify_patch(plan: PatchPlan, config: OmegaConfig) -> PatchPlan | None:
    return PatchPlanner(config).verify_patch(plan.id)


def produce_diff_summary(config: OmegaConfig) -> dict:
    return PatchPlanner(config).produce_diff_summary()


def _from_row(row) -> PatchPlan:
    proposed_json = row["proposed_changes_json"] or "[]"
    files_json = row["files_to_modify_json"] or "[]"
    metadata_json = row["metadata_json"] or "{}"
    return PatchPlan(
        id=row["id"],
        run_id=row["run_id"],
        project_id=row["project_id"],
        title=row["title"],
        problem=row["problem"],
        proposed_changes=_json_list_dict(proposed_json),
        proposed_changes_json=proposed_json,
        files_to_modify=_json_list_str(files_json),
        files_to_modify_json=files_json,
        risk_level=row["risk_level"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_json_dict(metadata_json),
        metadata_json=metadata_json,
    )


def _content_for_change(config: OmegaConfig, change: dict) -> str:
    if "content" in change:
        return str(change.get("content") or "")
    relative_path = str(change.get("relative_path") or change.get("path") or "")
    path = safe_path(config, relative_path)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    old = str(change.get("old") or "")
    new = str(change.get("new") or "")
    if old:
        return current.replace(old, new, 1)
    return new


def _files_from_changes(changes: list[dict]) -> list[str]:
    result = []
    for change in changes:
        path = str(change.get("relative_path") or change.get("path") or "").strip()
        if path and path not in result:
            result.append(path)
    return result


def _json_list_dict(value: str) -> list[dict]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _json_list_str(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
