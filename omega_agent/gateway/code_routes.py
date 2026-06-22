from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.runtime.code_agent import CodeWorkspaceAgent
from omega_agent.runtime.patch_planner import PatchPlanner
from omega_agent.runtime.repo_analyzer import RepoProfilesStore, summarize_repo
from omega_agent.runtime.self_healing import SelfHealingEngine
from omega_agent.runtime.test_runner import CodeTestRunner
from omega_agent.runtime.tool_broker import ToolBroker


def register_code_routes(router: APIRouter) -> None:
    @router.get("/api/code/repo")
    async def api_code_repo(request: Request, project_id: str | None = None):
        _ensure_enabled(request)
        store = RepoProfilesStore(_config(request))
        profile = store.get_latest(project_id=project_id)
        return (profile or summarize_repo(_config(request).workspace)).as_api()

    @router.post("/api/code/scan")
    async def api_code_scan(request: Request, payload: dict | None = None):
        _ensure_enabled(request)
        project_id = (payload or {}).get("project_id")
        return CodeWorkspaceAgent(_config(request)).scan(project_id=project_id)

    @router.get("/api/code/tests")
    async def api_code_tests(request: Request, project_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
        _ensure_enabled(request)
        return [item.as_api() for item in CodeTestRunner(_config(request)).list_runs(project_id=project_id, limit=limit)]

    @router.post("/api/code/tests/run")
    async def api_code_run_tests(request: Request, payload: dict | None = None):
        _ensure_enabled(request)
        payload = payload or {}
        command = str(payload.get("command") or "").strip() or None
        project_id = payload.get("project_id")
        return CodeWorkspaceAgent(_config(request)).test(command=command, project_id=project_id)

    @router.get("/api/code/patch-plans")
    async def api_code_patch_plans(request: Request, project_id: str | None = None):
        _ensure_enabled(request)
        return [item.as_api() for item in PatchPlanner(_config(request)).list_plans(project_id=project_id)]

    @router.post("/api/code/patch-plans")
    async def api_code_create_patch_plan(payload: dict, request: Request):
        _ensure_enabled(request)
        planner = PatchPlanner(_config(request))
        repo = summarize_repo(_config(request).workspace)
        plan = planner.create_patch_plan(
            str(payload.get("problem") or payload.get("error_summary") or ""),
            repo,
            proposed_changes=payload.get("proposed_changes") if isinstance(payload.get("proposed_changes"), list) else [],
            run_id=payload.get("run_id"),
            project_id=payload.get("project_id"),
            title=payload.get("title"),
        )
        return plan.as_api()

    @router.post("/api/code/patch-plans/{plan_id}/apply")
    async def api_code_apply_patch_plan(plan_id: str, request: Request, payload: dict | None = None):
        _ensure_enabled(request)
        session_id = (payload or {}).get("session_id")
        plan = PatchPlanner(_config(request)).apply_patch_plan(plan_id, session_id=session_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Patch plan introuvable.")
        return plan.as_api()

    @router.post("/api/code/patch-plans/{plan_id}/verify")
    async def api_code_verify_patch_plan(plan_id: str, request: Request):
        _ensure_enabled(request)
        plan = PatchPlanner(_config(request)).verify_patch(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Patch plan introuvable.")
        return plan.as_api()

    @router.get("/api/code/diff")
    async def api_code_diff(request: Request):
        _ensure_enabled(request)
        return PatchPlanner(_config(request)).produce_diff_summary()

    @router.post("/api/code/git/commit")
    async def api_code_git_commit(payload: dict, request: Request):
        _ensure_enabled(request)
        config = _config(request)
        if not config.code_allow_git_commit or not config.allow_git_write_in_workspace:
            raise HTTPException(status_code=403, detail="Git commit refuse par configuration.")
        message = str(payload.get("message") or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message de commit requis.")
        broker = ToolBroker(config)
        session_id = payload.get("session_id")
        if payload.get("add_all", True):
            add_result = broker.call("git_add", {"relative_path": "."}, session_id=session_id)
            if add_result.status != "completed":
                raise HTTPException(status_code=400, detail=add_result.output)
        commit = broker.call("git_commit", {"message": message}, session_id=session_id)
        if commit.status != "completed":
            raise HTTPException(status_code=400, detail=commit.output)
        request.app.state.gateway_state.events.add("git.commit.created", {"message": message}, session_id=session_id)
        return {"ok": True, "output": commit.output}

    @router.get("/api/self-healing/status")
    async def api_self_healing_status(request: Request):
        return SelfHealingEngine(_config(request)).status()

    @router.post("/api/self-healing/test")
    async def api_self_healing_test(payload: dict, request: Request):
        engine = SelfHealingEngine(_config(request))
        classified = engine.classify_error(str(payload.get("error") or ""), payload.get("context") if isinstance(payload.get("context"), dict) else {})
        suggestion = engine.suggest_recovery(classified.error_type, payload.get("context") if isinstance(payload.get("context"), dict) else {})
        return {"classified_error": classified.as_api(), "suggestion": suggestion.as_api()}


def _config(request: Request):
    return request.app.state.gateway_state.config


def _ensure_enabled(request: Request) -> None:
    if not _config(request).code_enabled:
        raise HTTPException(status_code=403, detail="Code Workspace desactive par configuration.")
