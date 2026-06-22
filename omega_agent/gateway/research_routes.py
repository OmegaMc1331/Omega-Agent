from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.gateway.models import ResearchExportRequest, ResearchStartRequest
from omega_agent.research.research_agent import OmegaResearchAgent


def register_research_routes(router: APIRouter) -> None:
    @router.get("/api/research")
    async def list_research_runs(request: Request, status: str | None = None, limit: int = Query(100, ge=1, le=500)):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        return [run.as_api() for run in agent.repository.list_runs(status=status, limit=limit)]

    @router.post("/api/research")
    async def start_research(payload: ResearchStartRequest, request: Request):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        try:
            run = agent.start(
                payload.question,
                title=payload.title,
                session_id=payload.session_id,
                manual_sources=payload.manual_sources,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return agent.detail(run.id)

    @router.get("/api/research/{research_run_id}")
    async def get_research_run(research_run_id: str, request: Request):
        try:
            return OmegaResearchAgent(request.app.state.gateway_state.config).detail(research_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/research/{research_run_id}/cancel")
    async def cancel_research_run(research_run_id: str, request: Request):
        try:
            return OmegaResearchAgent(request.app.state.gateway_state.config).cancel(research_run_id).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/research/{research_run_id}/sources")
    async def research_sources(research_run_id: str, request: Request):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        try:
            agent.repository.require_run(research_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [item.as_api() for item in agent.repository.list_sources(research_run_id)]

    @router.get("/api/research/{research_run_id}/claims")
    async def research_claims(research_run_id: str, request: Request):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        try:
            agent.repository.require_run(research_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [item.as_api() for item in agent.repository.list_claims(research_run_id)]

    @router.get("/api/research/{research_run_id}/evidence")
    async def research_evidence(research_run_id: str, request: Request):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        try:
            agent.repository.require_run(research_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return [item.as_api() for item in agent.repository.list_evidence(research_run_id)]

    @router.get("/api/research/{research_run_id}/graph")
    async def research_graph(research_run_id: str, request: Request):
        agent = OmegaResearchAgent(request.app.state.gateway_state.config)
        try:
            agent.repository.require_run(research_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return agent.repository.graph(research_run_id)

    @router.post("/api/research/{research_run_id}/export")
    async def export_research(research_run_id: str, payload: ResearchExportRequest, request: Request):
        try:
            return OmegaResearchAgent(request.app.state.gateway_state.config).export(research_run_id, payload.format)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
