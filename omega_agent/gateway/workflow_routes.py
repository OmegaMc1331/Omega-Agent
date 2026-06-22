from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.workflows.workflow_parser import parse_workflow_json
from omega_agent.workflows.workflow_runner import WorkflowRunner
from omega_agent.workflows.workflow_store import WorkflowStore
from omega_agent.workflows.workflow_validator import WorkflowValidationError
from omega_agent.shadow.shadow_runner import ShadowRunner


def register_workflow_routes(router: APIRouter) -> None:
    @router.get("/api/workflows/templates")
    async def api_workflow_templates(request: Request, category: str | None = None):
        store = WorkflowStore(request.app.state.gateway_state.config)
        return [template.as_api() for template in store.list_templates(category=category)]

    @router.get("/api/workflows/runs")
    async def api_workflow_runs(
        request: Request,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = Query(100, ge=1, le=500),
    ):
        store = WorkflowStore(request.app.state.gateway_state.config)
        return [run.as_api() for run in store.list_runs(workflow_id=workflow_id, status=status, limit=limit)]

    @router.get("/api/workflows/runs/{workflow_run_id}")
    async def api_workflow_run(workflow_run_id: str, request: Request):
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).get_workflow_run_status(workflow_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/workflows/runs/{workflow_run_id}/pause")
    async def api_pause_workflow_run(workflow_run_id: str, request: Request):
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).pause_workflow_run(workflow_run_id).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/workflows/runs/{workflow_run_id}/resume")
    async def api_resume_workflow_run(workflow_run_id: str, request: Request):
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).resume_workflow_run(workflow_run_id).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/workflows/runs/{workflow_run_id}/cancel")
    async def api_cancel_workflow_run(workflow_run_id: str, request: Request):
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).cancel_workflow_run(workflow_run_id).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/workflows/runs/{workflow_run_id}/retry-step")
    async def api_retry_workflow_step(workflow_run_id: str, request: Request):
        payload = await request.json()
        step_id = str(payload.get("step_id") or "")
        if not step_id:
            raise HTTPException(status_code=400, detail="step_id requis.")
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).retry_step(workflow_run_id, step_id).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/workflows")
    async def api_workflows(request: Request, enabled: bool | None = None, limit: int = Query(100, ge=1, le=500)):
        store = WorkflowStore(request.app.state.gateway_state.config)
        return [workflow.as_api() for workflow in store.list_workflows(enabled=enabled, limit=limit)]

    @router.post("/api/workflows")
    async def api_create_workflow(request: Request):
        payload = await request.json()
        definition = payload.get("definition") if isinstance(payload.get("definition"), dict) else payload
        if isinstance(definition, str):
            try:
                definition = parse_workflow_json(definition)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            workflow = WorkflowRunner(request.app.state.gateway_state.config).create_workflow(
                definition,
                enabled=bool(payload.get("enabled", True)) if isinstance(payload, dict) else True,
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        except (ValueError, WorkflowValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return workflow.as_api()

    @router.get("/api/workflows/{workflow_id}")
    async def api_get_workflow(workflow_id: str, request: Request):
        workflow = WorkflowStore(request.app.state.gateway_state.config).get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow introuvable.")
        return workflow.as_api()

    @router.patch("/api/workflows/{workflow_id}")
    async def api_patch_workflow(workflow_id: str, request: Request):
        payload = await request.json()
        runner = WorkflowRunner(request.app.state.gateway_state.config)
        if isinstance(payload.get("definition"), dict):
            try:
                payload["definition"] = runner.validate_workflow(payload["definition"])
            except (ValueError, WorkflowValidationError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        workflow = runner.store.update_workflow(workflow_id, payload)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow introuvable.")
        return workflow.as_api()

    @router.delete("/api/workflows/{workflow_id}")
    async def api_delete_workflow(workflow_id: str, request: Request):
        deleted = WorkflowStore(request.app.state.gateway_state.config).delete_workflow(workflow_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Workflow introuvable.")
        return {"ok": True}

    @router.post("/api/workflows/{workflow_id}/run")
    async def api_run_workflow(workflow_id: str, request: Request):
        payload = await _json_or_empty(request)
        try:
            workflow_run = WorkflowRunner(request.app.state.gateway_state.config).run_workflow(
                workflow_id,
                input=payload.get("input") if isinstance(payload.get("input"), dict) else {},
                session_id=payload.get("session_id"),
                shadow_run_id=payload.get("shadow_run_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return workflow_run.as_api()

    @router.get("/api/workflows/{workflow_id}/shadow-recommendation")
    async def api_workflow_shadow_recommendation(workflow_id: str, request: Request):
        try:
            return WorkflowRunner(request.app.state.gateway_state.config).shadow_recommendation(workflow_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/shadow")
    async def api_run_workflow_shadow(workflow_id: str, request: Request):
        workflow = WorkflowStore(request.app.state.gateway_state.config).get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow introuvable.")
        runner = ShadowRunner(request.app.state.gateway_state.config)
        shadow = runner.create_shadow_run(
            f"Workflow: {workflow.name}",
            source_type="workflow",
            source_id=workflow_id,
            metadata={"workflow_name": workflow.name},
        )
        return runner.run_shadow(shadow["id"])


async def _json_or_empty(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
