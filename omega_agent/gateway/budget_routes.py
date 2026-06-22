from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.governance.budget_store import BudgetStore
from omega_agent.governance.quota_tracker import QuotaTracker


class BudgetProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    scope_type: str = "global"
    scope_id: str | None = None
    limits: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetProfilePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    scope_type: str | None = None
    scope_id: str | None = None
    limits: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class BudgetSimulationRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)


def register_budget_routes(router: APIRouter) -> None:
    @router.get("/api/budgets/profiles")
    async def api_budget_profiles(request: Request, enabled: bool | None = Query(default=None)):
        return [item.as_api() for item in BudgetStore(request.app.state.gateway_state.config).list_profiles(enabled=enabled)]

    @router.post("/api/budgets/profiles")
    async def api_create_budget_profile(payload: BudgetProfileCreateRequest, request: Request):
        try:
            profile = BudgetStore(request.app.state.gateway_state.config).create_profile(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return profile.as_api()

    @router.get("/api/budgets/profiles/{profile_id}")
    async def api_budget_profile(profile_id: str, request: Request):
        profile = BudgetStore(request.app.state.gateway_state.config).get_profile(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Budget profile introuvable.")
        return profile.as_api()

    @router.patch("/api/budgets/profiles/{profile_id}")
    async def api_patch_budget_profile(profile_id: str, payload: BudgetProfilePatchRequest, request: Request):
        try:
            profile = BudgetStore(request.app.state.gateway_state.config).update_profile(profile_id, payload.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if profile is None:
            raise HTTPException(status_code=404, detail="Budget profile introuvable.")
        return profile.as_api()

    @router.delete("/api/budgets/profiles/{profile_id}")
    async def api_delete_budget_profile(profile_id: str, request: Request):
        if not BudgetStore(request.app.state.gateway_state.config).delete_profile(profile_id):
            raise HTTPException(status_code=404, detail="Budget profile introuvable.")
        return {"ok": True}

    @router.get("/api/budgets/usage")
    async def api_budget_usage(
        request: Request,
        run_id: str | None = Query(default=None),
        workflow_run_id: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
    ):
        tracker = QuotaTracker(request.app.state.gateway_state.config)
        return [item.as_api() for item in tracker.list(run_id=run_id, workflow_run_id=workflow_run_id, session_id=session_id, project_id=project_id)]

    @router.get("/api/budgets/violations")
    async def api_budget_violations(
        request: Request,
        run_id: str | None = Query(default=None),
        workflow_run_id: str | None = Query(default=None),
    ):
        store = BudgetStore(request.app.state.gateway_state.config)
        return [item.as_api() for item in store.list_violations(run_id=run_id, workflow_run_id=workflow_run_id)]

    @router.get("/api/budgets/effective")
    async def api_effective_budget(
        request: Request,
        run_id: str | None = Query(default=None),
        workflow_run_id: str | None = Query(default=None),
        workflow_id: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        agent_profile_id: str | None = Query(default=None),
    ):
        enforcer = BudgetEnforcer(request.app.state.gateway_state.config)
        context = enforcer.context(
            run_id=run_id,
            workflow_run_id=workflow_run_id,
            workflow_id=workflow_id,
            session_id=session_id,
            project_id=project_id,
            agent_profile_id=agent_profile_id,
        )
        return enforcer.get_effective_budget(context).as_api()

    @router.post("/api/budgets/simulate")
    async def api_simulate_budget(payload: BudgetSimulationRequest, request: Request):
        enforcer = BudgetEnforcer(request.app.state.gateway_state.config)
        context = enforcer.context(**payload.context)
        decision = enforcer.check_before_action(context, {**payload.action, "simulate": True})
        return {"decision": decision.as_api(), "effective_budget": enforcer.get_effective_budget(context).as_api()}
