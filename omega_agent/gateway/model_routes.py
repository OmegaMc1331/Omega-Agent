from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config, set_config_value
from omega_agent.runtime.model_selector import VALID_SCOPES


class ModelSelectRequest(BaseModel):
    model_ref: str = Field(min_length=3, max_length=300)
    scope: str = Field(default="session", max_length=32)
    scope_id: str | None = Field(default=None, max_length=128)
    fallback_model_ref: str | None = Field(default=None, max_length=300)


class ModelPreferencePatchRequest(BaseModel):
    scope: str = Field(max_length=32)
    scope_id: str | None = Field(default=None, max_length=128)
    primary_model_ref: str = Field(min_length=3, max_length=300)
    fallback_model_ref: str | None = Field(default=None, max_length=300)


class ModelTestRequest(BaseModel):
    model_ref: str = Field(min_length=3, max_length=300)
    prompt: str = Field(default="Réponds simplement: ok", max_length=2000)


def create_model_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/models/providers")
    async def providers(request: Request):
        return request.app.state.gateway_state.model_selector.providers_api()

    @router.get("/api/models/catalog")
    async def catalog(request: Request):
        return request.app.state.gateway_state.model_selector.catalog_api()

    @router.get("/api/models/status")
    async def status(request: Request):
        return request.app.state.gateway_state.model_selector.status_api()

    @router.get("/api/models/current")
    async def current(request: Request, session_id: str | None = None, project_id: str | None = None, agent_profile_id: str | None = None):
        return request.app.state.gateway_state.model_selector.current_api(session_id=session_id, project_id=project_id, agent_profile_id=agent_profile_id)

    @router.post("/api/models/select")
    async def select(payload: ModelSelectRequest, request: Request):
        scope = payload.scope
        if scope not in VALID_SCOPES:
            raise HTTPException(status_code=400, detail="Scope modèle invalide.")
        state = request.app.state.gateway_state
        try:
            preference = state.model_selector.set_preference(scope, payload.model_ref, scope_id=payload.scope_id, fallback_model_ref=payload.fallback_model_ref)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.events.add("model.changed", {"scope": scope, "scope_id": payload.scope_id, "model_ref": payload.model_ref})
        return preference.as_api()

    @router.post("/api/models/test")
    async def test_model(payload: ModelTestRequest, request: Request):
        state = request.app.state.gateway_state
        provider_id = payload.model_ref.split("/", 1)[0]
        provider = state.model_selector.provider(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider modèle inconnu.")
        auth = provider.check_auth()
        if auth.status != "configured" and provider.auth_type != "none":
            state.events.add("model.auth.missing", {"provider_id": provider_id, "model_ref": payload.model_ref})
            return {"ok": False, "status": auth.status, "message": "Authentification provider manquante.", "auth": auth.as_api()}
        return {"ok": True, "status": auth.status, "message": "Provider accessible pour test de configuration.", "auth": auth.as_api()}

    @router.post("/api/models/refresh")
    async def refresh(request: Request):
        result = request.app.state.gateway_state.model_selector.refresh_catalog()
        request.app.state.gateway_state.events.add("models.catalog.refreshed", result)
        return {"ok": True, **result}

    @router.get("/api/models/preferences")
    async def preferences(request: Request):
        return request.app.state.gateway_state.model_selector.preferences_api()

    @router.get("/api/models/usage")
    async def usage(request: Request):
        return request.app.state.gateway_state.model_selector.usage_api(limit=50)

    @router.patch("/api/models/preferences")
    async def patch_preferences(payload: ModelPreferencePatchRequest, request: Request):
        try:
            preference = request.app.state.gateway_state.model_selector.set_preference(payload.scope, payload.primary_model_ref, scope_id=payload.scope_id, fallback_model_ref=payload.fallback_model_ref)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.gateway_state.events.add("model.changed", {"scope": payload.scope, "scope_id": payload.scope_id, "model_ref": payload.primary_model_ref})
        return preference.as_api()

    @router.get("/api/models/providers/{provider_id}")
    async def provider(provider_id: str, request: Request):
        providers = [item for item in request.app.state.gateway_state.model_selector.providers_api() if item["id"] == provider_id]
        if not providers:
            raise HTTPException(status_code=404, detail="Provider introuvable.")
        return providers[0]

    @router.post("/api/models/providers/{provider_id}/enable")
    async def enable_provider(provider_id: str, request: Request):
        return _set_provider_enabled(request, provider_id, True)

    @router.post("/api/models/providers/{provider_id}/disable")
    async def disable_provider(provider_id: str, request: Request):
        return _set_provider_enabled(request, provider_id, False)

    @router.post("/api/models/providers/{provider_id}/test-auth")
    async def test_auth(provider_id: str, request: Request):
        provider = request.app.state.gateway_state.model_selector.provider(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider introuvable.")
        return provider.test_connection().as_api()

    @router.post("/api/models/providers/{provider_id}/refresh-catalog")
    async def refresh_provider_catalog(provider_id: str, request: Request):
        if request.app.state.gateway_state.model_selector.provider(provider_id) is None:
            raise HTTPException(status_code=404, detail="Provider introuvable.")
        result = request.app.state.gateway_state.model_selector.refresh_catalog(provider_id)
        request.app.state.gateway_state.events.add("models.catalog.refreshed", {"provider_id": provider_id, **result})
        return {"ok": True, **result}

    return router


def _set_provider_enabled(request: Request, provider_id: str, enabled: bool):
    state = request.app.state.gateway_state
    if state.model_selector.provider(provider_id) is None:
        raise HTTPException(status_code=404, detail="Provider introuvable.")
    from omega_agent.runtime.model_selector import _now
    from omega_agent.runtime.storage import connect_runtime_db

    with connect_runtime_db(state.config) as conn:
        conn.execute("UPDATE model_providers SET enabled = ?, updated_at = ? WHERE id = ?", (int(enabled), _now(), provider_id))
    if state.config.config_path is not None:
        data = set_config_value(f"providers.{provider_id}.enabled", enabled, file_path=state.config.config_path)
        save_config(data, state.config.config_path)
        state.config = OmegaConfig.from_env()
        state.model_selector = type(state.model_selector)(state.config)
    state.events.add("model.provider.enabled" if enabled else "model.provider.disabled", {"provider_id": provider_id})
    return {"ok": True, "provider_id": provider_id, "enabled": enabled}
