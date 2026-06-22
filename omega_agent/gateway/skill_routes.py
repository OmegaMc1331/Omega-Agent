from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.skills.foundry import SkillFoundry
from omega_agent.skills.skill_promoter import SkillPromoter
from omega_agent.skills.skill_store import SkillStore
from omega_agent.skills.skill_usage import SkillUsageStore


def register_skill_routes(router: APIRouter) -> None:
    @router.get("/api/skills/candidates")
    async def api_skill_candidates(request: Request, status: str | None = Query(default=None)):
        store = SkillStore(request.app.state.gateway_state.config)
        try:
            return [item.as_api() for item in store.list_candidates(status=status)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/skills/candidates/detect")
    async def api_detect_skill_candidates(request: Request):
        state = request.app.state.gateway_state
        candidates = SkillFoundry(state.config).detect_candidates()
        return [item.as_api() for item in candidates]

    @router.post("/api/skills/candidates/{candidate_id}/accept")
    async def api_accept_skill_candidate(candidate_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            skill = SkillPromoter(state.config).accept_candidate(candidate_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.reload_registries(log_event=False)
        return skill.as_api()

    @router.post("/api/skills/candidates/{candidate_id}/reject")
    async def api_reject_skill_candidate(candidate_id: str, request: Request):
        try:
            candidate = SkillPromoter(request.app.state.gateway_state.config).reject_candidate(candidate_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return candidate.as_api()

    @router.post("/api/skills/{skill_id}/test")
    async def api_test_skill(skill_id: str, request: Request):
        try:
            result = SkillPromoter(request.app.state.gateway_state.config).test_skill(skill_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return result.as_api()

    @router.post("/api/skills/{skill_id}/activate")
    async def api_activate_skill(skill_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            skill = SkillPromoter(state.config).activate(skill_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.reload_registries(log_event=False)
        return skill.as_api()

    @router.post("/api/skills/{skill_id}/disable")
    async def api_disable_skill(skill_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            skill = SkillPromoter(state.config).disable(skill_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        state.reload_registries(log_event=False)
        return skill.as_api()

    @router.get("/api/skills/{skill_id}/usage")
    async def api_skill_usage(skill_id: str, request: Request):
        store = SkillStore(request.app.state.gateway_state.config)
        if store.get_skill(skill_id) is None:
            raise HTTPException(status_code=404, detail="Skill introuvable.")
        usage = SkillUsageStore(request.app.state.gateway_state.config)
        return {
            "summary": usage.summary(skill_id),
            "events": [item.as_api() for item in usage.list(skill_id)],
        }

    @router.get("/api/skills/{skill_id}")
    async def api_skill_detail(skill_id: str, request: Request):
        store = SkillStore(request.app.state.gateway_state.config)
        skill = store.get_skill(skill_id)
        if skill is None:
            legacy = request.app.state.gateway_state.skills_list()
            item = next((entry for entry in legacy if entry.id == skill_id or entry.name == skill_id), None)
            if item is None:
                raise HTTPException(status_code=404, detail="Skill introuvable.")
            from dataclasses import asdict

            return {"skill": asdict(item), "versions": [], "tests": [], "usage": {"count": 0, "last_used": None}}
        usage = SkillUsageStore(request.app.state.gateway_state.config)
        return {
            "skill": skill.as_api(),
            "versions": [item.as_api() for item in store.list_versions(skill.id)],
            "tests": [item.as_api() for item in store.list_test_runs(skill.id)],
            "usage": usage.summary(skill.id),
        }
