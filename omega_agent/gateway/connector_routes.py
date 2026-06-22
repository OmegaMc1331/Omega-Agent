from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.security.sandbox import safe_path


class ConnectorCreateRequest(BaseModel):
    id: str | None = None
    type: str = "custom"
    name: str
    description: str = ""
    enabled: bool = False
    trust_level: str = "untrusted"
    auth_type: str = "none"
    auth_ref: str | None = None
    base_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    operations: list[dict] = Field(default_factory=list)
    risk_level: str = "medium"
    metadata: dict = Field(default_factory=dict)


class ConnectorPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    trust_level: str | None = None
    auth_type: str | None = None
    auth_ref: str | None = None
    base_url: str | None = None
    scopes: list[str] | None = None
    risk_level: str | None = None
    metadata: dict | None = None


class OpenAPIImportRequest(BaseModel):
    path: str | None = None
    document: dict | str | None = None
    name: str | None = None
    base_url: str | None = None
    trust_level: str = "local"
    source: str | None = None


def register_connector_routes(router: APIRouter) -> None:
    @router.get("/api/connectors")
    async def list_connectors(request: Request, type: str | None = None, enabled: bool | None = None, q: str | None = None):
        registry = ConnectorsRegistry(request.app.state.gateway_state.config)
        return [item.as_api() for item in registry.list(type=type, enabled=enabled, query=q)]

    @router.post("/api/connectors")
    async def create_connector(payload: ConnectorCreateRequest, request: Request):
        try:
            connector = ConnectorsRegistry(request.app.state.gateway_state.config).create(_payload(payload))
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return connector.as_api()

    @router.get("/api/connectors/usage")
    async def connector_usage(request: Request, connector_id: str | None = None, limit: int = 100):
        registry = ConnectorsRegistry(request.app.state.gateway_state.config)
        return [item.as_api() for item in registry.usage.list(connector_id=connector_id, limit=limit)]

    @router.get("/api/connectors/auth-status")
    async def connector_auth_status(request: Request):
        return ConnectorsRegistry(request.app.state.gateway_state.config).auth_status()

    @router.post("/api/connectors/openapi/import")
    async def import_openapi(payload: OpenAPIImportRequest, request: Request):
        config = request.app.state.gateway_state.config
        path = None
        if payload.path:
            try:
                path = safe_path(config, payload.path)
            except Exception as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            connector = ConnectorsRegistry(config).import_openapi(
                path,
                document=payload.document,
                name=payload.name,
                base_url=payload.base_url,
                trust_level=payload.trust_level,
                source=payload.source or str(path or "inline"),
            )
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return connector.as_api()

    @router.get("/api/connectors/{connector_id}")
    async def get_connector(connector_id: str, request: Request):
        connector = ConnectorsRegistry(request.app.state.gateway_state.config).get(connector_id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return connector.as_api()

    @router.patch("/api/connectors/{connector_id}")
    async def patch_connector(connector_id: str, payload: ConnectorPatchRequest, request: Request):
        try:
            connector = ConnectorsRegistry(request.app.state.gateway_state.config).patch(connector_id, _payload(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if connector is None:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return connector.as_api()

    @router.delete("/api/connectors/{connector_id}")
    async def delete_connector(connector_id: str, request: Request):
        try:
            deleted = ConnectorsRegistry(request.app.state.gateway_state.config).delete(connector_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return {"ok": True}

    @router.get("/api/connectors/{connector_id}/operations")
    async def connector_operations(connector_id: str, request: Request):
        registry = ConnectorsRegistry(request.app.state.gateway_state.config)
        if registry.get(connector_id) is None:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return [operation.as_api() for operation in registry.operations(connector_id)]

    @router.post("/api/connectors/{connector_id}/test")
    async def test_connector(connector_id: str, request: Request):
        try:
            return ConnectorsRegistry(request.app.state.gateway_state.config).test_connector(connector_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.") from exc

    @router.post("/api/connectors/{connector_id}/enable")
    async def enable_connector(connector_id: str, request: Request):
        connector = ConnectorsRegistry(request.app.state.gateway_state.config).enable(connector_id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return connector.as_api()

    @router.post("/api/connectors/{connector_id}/disable")
    async def disable_connector(connector_id: str, request: Request):
        connector = ConnectorsRegistry(request.app.state.gateway_state.config).disable(connector_id)
        if connector is None:
            raise HTTPException(status_code=404, detail="Connecteur introuvable.")
        return connector.as_api()


def _payload(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)
