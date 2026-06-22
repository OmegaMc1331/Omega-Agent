from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.events import EventBus, EventStore
from omega_agent.security.redaction import redact


def register_event_routes(router: APIRouter) -> None:
    @router.get("/api/events/v2")
    async def api_events_v2(
        request: Request,
        limit: int = Query(100, ge=1, le=1000),
        type: str | None = None,
        source: str | None = None,
        level: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ):
        store = EventStore(request.app.state.gateway_state.config)
        return [
            event.as_api()
            for event in store.list(
                limit=limit,
                type=type,
                source=source,
                level=level,
                session_id=session_id,
                run_id=run_id,
                for_ui=True,
            )
        ]

    @router.get("/api/events/v2/replay")
    async def api_events_v2_replay(
        request: Request,
        since_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = Query(None, ge=1, le=1000),
    ):
        events = EventBus(request.app.state.gateway_state.config).replay_events(
            since_id=since_id,
            session_id=session_id,
            run_id=run_id,
            limit=limit,
        )
        return [event.as_api() for event in events]

    @router.get("/api/events/v2/types")
    async def api_events_v2_types(request: Request):
        return {"types": EventStore(request.app.state.gateway_state.config).types()}

    @router.post("/api/events/v2/test")
    async def api_events_v2_test(request: Request, payload: dict | None = None):
        payload = payload or {}
        event_type = str(payload.get("type") or "system.test")
        event_payload = redact(payload.get("payload") if isinstance(payload.get("payload"), dict) else {"ok": True})
        event = EventBus(request.app.state.gateway_state.config).emit(
            event_type,
            event_payload,
            session_id=payload.get("session_id"),
            run_id=payload.get("run_id"),
            source="gateway",
            level=str(payload.get("level") or "info"),
            visibility=str(payload.get("visibility") or "public"),
        )
        return event.as_api()

    @router.get("/api/events/v2/{event_id}")
    async def api_events_v2_get(event_id: str, request: Request):
        event = EventStore(request.app.state.gateway_state.config).get(event_id, for_ui=True)
        if event is None:
            raise HTTPException(status_code=404, detail="Event introuvable.")
        return event.as_api()
