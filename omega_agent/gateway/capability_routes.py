from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.runtime.a2a_agents import A2AAgentsRegistry
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.capability_usage import CapabilityUsageStore
from omega_agent.runtime.mcp_servers import MCPServersRegistry


def register_capability_routes(router: APIRouter) -> None:
    @router.get("/api/capabilities")
    async def api_capabilities(
        request: Request,
        type: str | None = None,
        risk_level: str | None = None,
        enabled: bool | None = None,
        auth_status: str | None = None,
        q: str | None = None,
    ):
        registry = CapabilitiesRegistry(request.app.state.gateway_state.config)
        return [
            capability.as_api()
            for capability in registry.list(type=type, risk_level=risk_level, enabled=enabled, auth_status=auth_status, query=q)
        ]

    @router.post("/api/capabilities/refresh")
    async def api_capabilities_refresh(request: Request):
        return CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()

    @router.get("/api/capabilities/usage")
    async def api_capabilities_usage(request: Request, capability_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
        return [event.as_api() for event in CapabilityUsageStore(request.app.state.gateway_state.config).list(limit=limit, capability_id=capability_id)]

    @router.get("/api/capabilities/{capability_id:path}")
    async def api_get_capability(capability_id: str, request: Request):
        capability = CapabilitiesRegistry(request.app.state.gateway_state.config).get(capability_id)
        if capability is None:
            raise HTTPException(status_code=404, detail="Capability introuvable.")
        return capability.as_api()

    @router.patch("/api/capabilities/{capability_id:path}")
    async def api_patch_capability(capability_id: str, request: Request):
        payload = await request.json()
        try:
            capability = CapabilitiesRegistry(request.app.state.gateway_state.config).patch(capability_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if capability is None:
            raise HTTPException(status_code=404, detail="Capability introuvable.")
        return capability.as_api()

    @router.get("/api/mcp/servers")
    async def api_mcp_servers(request: Request):
        return [server.as_api() for server in MCPServersRegistry(request.app.state.gateway_state.config).list()]

    @router.post("/api/mcp/servers")
    async def api_add_mcp_server(request: Request):
        payload = await request.json()
        try:
            server = MCPServersRegistry(request.app.state.gateway_state.config).add(
                name=str(payload.get("name") or ""),
                url=payload.get("url"),
                command=payload.get("command"),
                description=str(payload.get("description") or ""),
                trust_level=str(payload.get("trust_level") or "untrusted"),
                scopes=list(payload.get("scopes") or []),
                auth_ref=payload.get("auth_ref"),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return server.as_api()

    @router.patch("/api/mcp/servers/{server_id}")
    async def api_patch_mcp_server(server_id: str, request: Request):
        payload = await request.json()
        try:
            server = MCPServersRegistry(request.app.state.gateway_state.config).patch(server_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if server is None:
            raise HTTPException(status_code=404, detail="MCP server introuvable.")
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return server.as_api()

    @router.delete("/api/mcp/servers/{server_id}")
    async def api_delete_mcp_server(server_id: str, request: Request):
        deleted = MCPServersRegistry(request.app.state.gateway_state.config).delete(server_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="MCP server introuvable.")
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return {"ok": True}

    @router.get("/api/a2a/agents")
    async def api_a2a_agents(request: Request):
        return [agent.as_api() for agent in A2AAgentsRegistry(request.app.state.gateway_state.config).list()]

    @router.post("/api/a2a/agents")
    async def api_add_a2a_agent(request: Request):
        payload = await request.json()
        try:
            agent = A2AAgentsRegistry(request.app.state.gateway_state.config).add(
                name=str(payload.get("name") or ""),
                endpoint=payload.get("endpoint"),
                description=str(payload.get("description") or ""),
                agent_card=payload.get("agent_card") if isinstance(payload.get("agent_card"), dict) else {},
                trust_level=str(payload.get("trust_level") or "untrusted"),
                scopes=list(payload.get("scopes") or []),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return agent.as_api()

    @router.patch("/api/a2a/agents/{agent_id}")
    async def api_patch_a2a_agent(agent_id: str, request: Request):
        payload = await request.json()
        try:
            agent = A2AAgentsRegistry(request.app.state.gateway_state.config).patch(agent_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if agent is None:
            raise HTTPException(status_code=404, detail="A2A agent introuvable.")
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return agent.as_api()

    @router.delete("/api/a2a/agents/{agent_id}")
    async def api_delete_a2a_agent(agent_id: str, request: Request):
        deleted = A2AAgentsRegistry(request.app.state.gateway_state.config).delete(agent_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="A2A agent introuvable.")
        CapabilitiesRegistry(request.app.state.gateway_state.config).refresh()
        return {"ok": True}
