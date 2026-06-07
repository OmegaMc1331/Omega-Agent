from __future__ import annotations

import inspect

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from omega_agent.codex_backend import CODEX_LOGIN_HINT
from omega_agent.gateway.routes import CODEX_DISCONNECTED_MESSAGE
from omega_agent.runtime.reasoning import ReasoningEvent


def create_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def ws_global(websocket: WebSocket):
        await websocket.accept()
        state = websocket.app.state.gateway_state
        await websocket.send_json({"type": "status.updated", "payload": {"status": "connected"}})
        try:
            while True:
                payload = await websocket.receive_json()
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
                    await websocket.send_json({"type": "message.accepted", "session_id": session_id, "payload": {"status": "accepted"}})
                    await websocket.send_json({"type": "message.created", "session_id": session_id, "role": "user", "content": message})
                    try:
                        output = await _send_message_with_reasoning(state.runtime(), websocket, message, session_id)
                    except PermissionError as exc:
                        await websocket.send_json({"type": "error", "payload": {"message": str(exc)}})
                        continue
                    if output == CODEX_LOGIN_HINT:
                        output = CODEX_DISCONNECTED_MESSAGE
                    await websocket.send_json({"type": "message.delta", "session_id": session_id, "role": "assistant", "content": output})
                    await websocket.send_json({"type": "message.completed", "session_id": session_id, "role": "assistant", "content": output})
                else:
                    await websocket.send_json({"type": "status.updated", "payload": {"status": "idle"}})
        except WebSocketDisconnect:
            return

    @router.websocket("/ws/chat/{session_id}")
    async def ws_chat(websocket: WebSocket, session_id: str):
        await websocket.accept()
        state = websocket.app.state.gateway_state
        if state.sessions.get_session(session_id) is None:
            await websocket.send_json({"type": "error", "message": "Session introuvable."})
            await websocket.close()
            return
        try:
            while True:
                payload = await websocket.receive_json()
                message = str(payload.get("message", "")).strip()
                if not message:
                    await websocket.send_json({"type": "error", "message": "Message vide."})
                    continue
                await websocket.send_json({"type": "message.accepted", "session_id": session_id, "payload": {"status": "accepted"}})
                await websocket.send_json({"type": "message.created", "role": "user", "content": message})
                try:
                    output = await _send_message_with_reasoning(state.runtime(), websocket, message, session_id)
                except PermissionError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                if output == CODEX_LOGIN_HINT:
                    output = CODEX_DISCONNECTED_MESSAGE
                await websocket.send_json({"type": "message.delta", "role": "assistant", "content": output})
                await websocket.send_json({"type": "message.completed", "role": "assistant", "content": output})
        except WebSocketDisconnect:
            return

    return router


async def _send_message_with_reasoning(runtime, websocket: WebSocket, message: str, session_id: str) -> str:
    async def sink(event: ReasoningEvent) -> None:
        await websocket.send_json(_reasoning_ws_payload(event))

    signature = inspect.signature(runtime.send_message)
    if "reasoning_sink" in signature.parameters:
        return await runtime.send_message(message, session_id=session_id, reasoning_sink=sink)
    return await runtime.send_message(message, session_id=session_id)


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
