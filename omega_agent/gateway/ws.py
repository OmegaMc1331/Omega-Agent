from __future__ import annotations

import asyncio
import inspect

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from omega_agent.codex_backend import CODEX_LOGIN_HINT
from omega_agent.events.event_bus import EventBus, event_ws_message
from omega_agent.gateway.routes import CODEX_DISCONNECTED_MESSAGE
from omega_agent.runtime.reasoning import ReasoningEvent


def create_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def ws_global(websocket: WebSocket):
        await websocket.accept()
        state = websocket.app.state.gateway_state
        bus = EventBus(state.config)
        subscription = bus.subscribe()
        last_event_id = websocket.query_params.get("last_event_id")
        await websocket.send_json({"type": "status.updated", "payload": {"status": "connected"}})
        await _send_replay(websocket, bus, last_event_id=last_event_id)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(websocket.receive_json(), timeout=state.config.events_websocket_heartbeat_seconds)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "connection.heartbeat", "payload": {"status": "connected"}})
                    await _drain_events(websocket, subscription)
                    continue
                event_type = str(payload.get("type") or "")
                if event_type == "chat.send":
                    session_id = str(payload.get("session_id") or "")
                    if not session_id or state.sessions.get_session(session_id) is None:
                        await websocket.send_json({"type": "error", "payload": {"message": "Session introuvable ou manquante."}})
                        continue
                    message = str(payload.get("message") or "").strip()
                    if not message:
                        await websocket.send_json({"type": "error", "payload": {"message": "Message vide."}})
                        continue
                    bus.emit("chat.message.received", {"session_id": session_id}, session_id=session_id, source="gateway")
                    await websocket.send_json({"type": "message.accepted", "session_id": session_id, "payload": {"status": "accepted"}})
                    bus.emit("message.created", {"session_id": session_id, "role": "user", "content": message}, session_id=session_id, source="gateway")
                    await websocket.send_json({"type": "message.created", "session_id": session_id, "role": "user", "content": message})
                    try:
                        output = await _send_message_with_reasoning(state.runtime(), websocket, message, session_id, state.config)
                    except PermissionError as exc:
                        await websocket.send_json({"type": "error", "payload": {"message": str(exc)}})
                        continue
                    if output == CODEX_LOGIN_HINT:
                        output = CODEX_DISCONNECTED_MESSAGE
                    bus.emit("message.delta", {"session_id": session_id, "role": "assistant", "content": output}, session_id=session_id, source="gateway")
                    await websocket.send_json({"type": "message.delta", "session_id": session_id, "role": "assistant", "content": output})
                    bus.emit("message.completed", {"session_id": session_id, "role": "assistant", "content": output}, session_id=session_id, source="gateway")
                    await websocket.send_json({"type": "message.completed", "session_id": session_id, "role": "assistant", "content": output})
                    await _drain_events(websocket, subscription)
                elif event_type == "events.replay":
                    await _send_replay(
                        websocket,
                        bus,
                        last_event_id=str(payload.get("last_event_id") or payload.get("since_id") or ""),
                        session_id=payload.get("session_id"),
                        run_id=payload.get("run_id"),
                        allow_without_cursor=True,
                    )
                else:
                    await websocket.send_json({"type": "status.updated", "payload": {"status": "idle"}})
                    await _drain_events(websocket, subscription)
        except WebSocketDisconnect:
            return
        finally:
            bus.unsubscribe(subscription)

    @router.websocket("/ws/chat/{session_id}")
    async def ws_chat(websocket: WebSocket, session_id: str):
        await websocket.accept()
        state = websocket.app.state.gateway_state
        bus = EventBus(state.config)
        subscription = bus.subscribe()
        await _send_replay(websocket, bus, last_event_id=websocket.query_params.get("last_event_id"), session_id=session_id)
        if state.sessions.get_session(session_id) is None:
            await websocket.send_json({"type": "error", "message": "Session introuvable."})
            await websocket.close()
            bus.unsubscribe(subscription)
            return
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(websocket.receive_json(), timeout=state.config.events_websocket_heartbeat_seconds)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "connection.heartbeat", "payload": {"status": "connected"}})
                    await _drain_events(websocket, subscription)
                    continue
                message = str(payload.get("message", "")).strip()
                if not message:
                    await websocket.send_json({"type": "error", "message": "Message vide."})
                    continue
                bus.emit("chat.message.received", {"session_id": session_id}, session_id=session_id, source="gateway")
                await websocket.send_json({"type": "message.accepted", "session_id": session_id, "payload": {"status": "accepted"}})
                bus.emit("message.created", {"session_id": session_id, "role": "user", "content": message}, session_id=session_id, source="gateway")
                await websocket.send_json({"type": "message.created", "role": "user", "content": message})
                try:
                    output = await _send_message_with_reasoning(state.runtime(), websocket, message, session_id, state.config)
                except PermissionError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                if output == CODEX_LOGIN_HINT:
                    output = CODEX_DISCONNECTED_MESSAGE
                bus.emit("message.delta", {"session_id": session_id, "role": "assistant", "content": output}, session_id=session_id, source="gateway")
                await websocket.send_json({"type": "message.delta", "role": "assistant", "content": output})
                bus.emit("message.completed", {"session_id": session_id, "role": "assistant", "content": output}, session_id=session_id, source="gateway")
                await websocket.send_json({"type": "message.completed", "role": "assistant", "content": output})
                await _drain_events(websocket, subscription)
        except WebSocketDisconnect:
            return
        finally:
            bus.unsubscribe(subscription)

    return router


async def _send_message_with_reasoning(runtime, websocket: WebSocket, message: str, session_id: str, config=None) -> str:
    runtime_config = config or getattr(runtime, "config", None)
    bus = EventBus(runtime_config) if runtime_config is not None else None

    async def sink(event: ReasoningEvent) -> None:
        if bus is not None:
            bus.emit(
                event.type,
                event.as_api(),
                session_id=event.session_id,
                source="runtime",
                visibility=event.visibility,
                metadata={"message_id": event.message_id},
            )
        await websocket.send_json(_reasoning_ws_payload(event))

    signature = inspect.signature(runtime.send_message)
    if "reasoning_sink" in signature.parameters:
        return await runtime.send_message(message, session_id=session_id, reasoning_sink=sink)
    return await runtime.send_message(message, session_id=session_id)


async def _send_replay(
    websocket: WebSocket,
    bus: EventBus,
    *,
    last_event_id: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    allow_without_cursor: bool = False,
) -> None:
    if not allow_without_cursor and not last_event_id:
        return
    events = bus.replay_events(
        since_id=last_event_id or None,
        session_id=session_id,
        run_id=run_id,
        limit=bus.config.events_max_replay_events,
    )
    for event in events:
        await websocket.send_json(event_ws_message(event))


async def _drain_events(websocket: WebSocket, subscription) -> None:
    while True:
        try:
            message = subscription.queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        await websocket.send_json(message)


def _reasoning_ws_payload(event: ReasoningEvent) -> dict:
    event_type = {
        "reasoning.tool_requested": "tool.requested",
        "reasoning.tool_started": "tool.started",
        "reasoning.tool_completed": "tool.completed",
        "reasoning.approval_required": "approval.required",
    }.get(event.type, event.type)
    payload = event.as_api()
    payload["reasoning_type"] = event.type
    return {"type": event_type, "session_id": event.session_id, "message_id": event.message_id, "payload": payload}
