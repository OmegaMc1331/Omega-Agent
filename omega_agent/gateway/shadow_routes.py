from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from omega_agent.shadow.shadow_runner import ShadowRunner


class ShadowCreateRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=10000)
    source_type: str = "manual_plan"
    source_id: str | None = None
    plan: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowPromoteRequest(BaseModel):
    approved_by: str | None = Field(default=None, max_length=200)


def register_shadow_routes(router: APIRouter) -> None:
    @router.get("/api/shadow")
    async def api_shadow_runs(request: Request, status: str | None = None, limit: int = Query(100, ge=1, le=500)):
        return ShadowRunner(request.app.state.gateway_state.config).list_shadow_runs(status=status, limit=limit)

    @router.post("/api/shadow")
    async def api_create_shadow(payload: ShadowCreateRequest, request: Request):
        try:
            return ShadowRunner(request.app.state.gateway_state.config).create_shadow_run(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/shadow/{shadow_run_id}")
    async def api_shadow_run(shadow_run_id: str, request: Request):
        item = ShadowRunner(request.app.state.gateway_state.config).get_shadow_run(shadow_run_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Shadow run introuvable.")
        return item

    @router.post("/api/shadow/{shadow_run_id}/run")
    async def api_run_shadow(shadow_run_id: str, request: Request):
        try:
            return ShadowRunner(request.app.state.gateway_state.config).run_shadow(shadow_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/shadow/{shadow_run_id}/promote")
    async def api_promote_shadow(shadow_run_id: str, payload: ShadowPromoteRequest, request: Request):
        try:
            return ShadowRunner(request.app.state.gateway_state.config).promote_to_live(shadow_run_id, approved_by=payload.approved_by)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/shadow/{shadow_run_id}/reject")
    async def api_reject_shadow(shadow_run_id: str, request: Request):
        try:
            return ShadowRunner(request.app.state.gateway_state.config).reject(shadow_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/shadow/{shadow_run_id}/diff")
    async def api_shadow_diff(shadow_run_id: str, request: Request):
        runner = ShadowRunner(request.app.state.gateway_state.config)
        item = runner.get_shadow_run(shadow_run_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Shadow run introuvable.")
        return item.get("predicted_diff") or runner.collect_predicted_diff(shadow_run_id)

    @router.get("/api/shadow/{shadow_run_id}/risk")
    async def api_shadow_risk(shadow_run_id: str, request: Request):
        runner = ShadowRunner(request.app.state.gateway_state.config)
        item = runner.get_shadow_run(shadow_run_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Shadow run introuvable.")
        return item.get("risk_report") or runner.compute_risk_report(shadow_run_id)

    @router.get("/api/shadow/{shadow_run_id}/comparison")
    async def api_shadow_comparison(shadow_run_id: str, request: Request):
        runner = ShadowRunner(request.app.state.gateway_state.config)
        if runner.get_shadow_run(shadow_run_id) is None:
            raise HTTPException(status_code=404, detail="Shadow run introuvable.")
        return runner.get_comparison(shadow_run_id)
