from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from omega_agent.security.audit import run_security_audit
from omega_agent.security.policy_profiles import PolicyProfilesStore, PolicyRulesStore
from omega_agent.security.policy_simulator import PolicySimulator


def register_policy_routes(router: APIRouter) -> None:
    @router.get("/api/policy/profiles")
    async def api_policy_profiles(request: Request):
        return [profile.as_api() for profile in PolicyProfilesStore(request.app.state.gateway_state.config).list()]

    @router.post("/api/policy/profiles")
    async def api_policy_profiles_create(request: Request, payload: dict):
        try:
            profile = PolicyProfilesStore(request.app.state.gateway_state.config).create(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return profile.as_api()

    @router.patch("/api/policy/profiles/{profile_id}")
    async def api_policy_profiles_patch(request: Request, profile_id: str, payload: dict):
        try:
            profile = PolicyProfilesStore(request.app.state.gateway_state.config).patch(profile_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return profile.as_api()

    @router.delete("/api/policy/profiles/{profile_id}")
    async def api_policy_profiles_delete(request: Request, profile_id: str):
        PolicyProfilesStore(request.app.state.gateway_state.config).delete(profile_id)
        return {"ok": True}

    @router.get("/api/policy/rules")
    async def api_policy_rules(request: Request, profile_id: str | None = None):
        return [rule.as_api() for rule in PolicyRulesStore(request.app.state.gateway_state.config).list(profile_id=profile_id)]

    @router.post("/api/policy/rules")
    async def api_policy_rules_create(request: Request, payload: dict):
        try:
            rule = PolicyRulesStore(request.app.state.gateway_state.config).create(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return rule.as_api()

    @router.patch("/api/policy/rules/{rule_id}")
    async def api_policy_rules_patch(request: Request, rule_id: str, payload: dict):
        try:
            rule = PolicyRulesStore(request.app.state.gateway_state.config).patch(rule_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return rule.as_api()

    @router.delete("/api/policy/rules/{rule_id}")
    async def api_policy_rules_delete(request: Request, rule_id: str):
        PolicyRulesStore(request.app.state.gateway_state.config).delete(rule_id)
        return {"ok": True}

    @router.post("/api/policy/simulate")
    async def api_policy_simulate(request: Request, payload: dict):
        return PolicySimulator(request.app.state.gateway_state.config).simulate_policy(payload)

    @router.get("/api/policy/audit")
    async def api_policy_audit(request: Request):
        report = run_security_audit(request.app.state.gateway_state.config).as_api()
        report["findings"] = [item for item in report["findings"] if item.get("area") == "policy"]
        return report

    @router.get("/api/policy/effective")
    async def api_policy_effective(request: Request):
        config = request.app.state.gateway_state.config
        return {
            "profiles": [profile.as_api() for profile in PolicyProfilesStore(config).list(include_disabled=False)],
            "rules": [rule.as_api() for rule in PolicyRulesStore(config).list(include_disabled=False)],
        }
