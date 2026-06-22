from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket

from omega_agent.config import OmegaConfig
from omega_agent.events.event_redaction import event_for_ui, redact_event
from omega_agent.events.event_store import EventStore
from omega_agent.events.event_subscriptions import EventSubscription
from omega_agent.events.protocol import OmegaEvent, infer_level, infer_source
from omega_agent.runtime.context import current_runtime_mode
from omega_agent.storage.db import db_path

_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = defaultdict(list)


class EventBus:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = EventStore(config)

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
        source: str | None = None,
        level: str | None = None,
        visibility: str = "public",
        metadata: dict[str, Any] | None = None,
    ) -> OmegaEvent:
        if not getattr(self.config, "events_enabled", True):
            return OmegaEvent.create(
                event_type,
                payload or {},
                session_id=session_id,
                run_id=run_id,
                step_id=step_id,
                user_id=user_id,
                source=source or infer_source(event_type),
                level=level or infer_level(event_type),
                visibility=visibility,
                metadata=metadata,
            )
        event = OmegaEvent.create(
            event_type,
            payload or {},
            session_id=session_id,
            run_id=run_id,
            step_id=step_id,
            user_id=user_id,
            source=source or infer_source(event_type),
            level=level or infer_level(event_type),
            visibility=visibility,
            metadata=metadata,
        )
        if getattr(self.config, "events_redaction_enabled", True):
            event = redact_event(event, max_chars=_max_trace_chars(self.config))
        if getattr(self.config, "events_persist", True):
            self.store.persist(event)
        if current_runtime_mode() != "cli":
            self._publish(event)
        return event

    def subscribe(self, channel: str = "public") -> EventSubscription:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        _SUBSCRIBERS[self._subscriber_key()].append(queue)
        return EventSubscription(channel=channel, queue=queue)

    def unsubscribe(self, subscription: EventSubscription) -> None:
        subscribers = _SUBSCRIBERS.get(self._subscriber_key(), [])
        if subscription.queue in subscribers:
            subscribers.remove(subscription.queue)

    def replay_events(
        self,
        *,
        since_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[OmegaEvent]:
        if not getattr(self.config, "events_replay_enabled", True):
            return []
        return self.store.replay(since_id=since_id, session_id=session_id, run_id=run_id, limit=limit, for_ui=True)

    async def publish_to_websocket(self, websocket: WebSocket, event: OmegaEvent) -> None:
        view = event_for_ui(event, max_chars=_max_trace_chars(self.config))
        if view is None:
            return
        await websocket.send_json(event_ws_message(view))

    def _publish(self, event: OmegaEvent) -> None:
        view = event_for_ui(event, max_chars=_max_trace_chars(self.config))
        if view is None:
            return
        message = event_ws_message(view)
        stale: list[asyncio.Queue] = []
        for queue in list(_SUBSCRIBERS.get(self._subscriber_key(), [])):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except Exception:
                    stale.append(queue)
            except RuntimeError:
                stale.append(queue)
        if stale:
            subscribers = _SUBSCRIBERS.get(self._subscriber_key(), [])
            for queue in stale:
                if queue in subscribers:
                    subscribers.remove(queue)

    def _subscriber_key(self) -> str:
        return str(db_path(self.config))


def event_ws_message(event: OmegaEvent | dict) -> dict[str, Any]:
    data = event.as_api() if isinstance(event, OmegaEvent) else event
    return {
        "type": data.get("type"),
        "event_id": data.get("id") or data.get("event_id"),
        "version": data.get("version"),
        "timestamp": data.get("timestamp"),
        "session_id": data.get("session_id"),
        "run_id": data.get("run_id"),
        "step_id": data.get("step_id"),
        "source": data.get("source"),
        "level": data.get("level"),
        "visibility": data.get("visibility"),
        "payload": data.get("payload") or {},
        "metadata": data.get("metadata") or {},
        "event": data,
    }


def event_from_ws_message(message: dict[str, Any]) -> OmegaEvent:
    event = message.get("event") if isinstance(message.get("event"), dict) else message
    return OmegaEvent(
        id=str(event.get("id") or event.get("event_id") or ""),
        version=str(event.get("version") or "ag-ui.v1"),
        type=str(event.get("type") or "system.event"),
        timestamp=str(event.get("timestamp") or ""),
        session_id=event.get("session_id"),
        run_id=event.get("run_id"),
        step_id=event.get("step_id"),
        user_id=event.get("user_id"),
        source=str(event.get("source") or "runtime"),
        level=str(event.get("level") or "info"),
        visibility=str(event.get("visibility") or "public"),
        payload=event.get("payload") if isinstance(event.get("payload"), dict) else {},
        metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
    )


def with_metadata(event: OmegaEvent, metadata: dict[str, Any]) -> OmegaEvent:
    next_metadata = dict(event.metadata)
    next_metadata.update(metadata)
    return replace(event, metadata=next_metadata)


def _max_trace_chars(config: OmegaConfig) -> int:
    return max(1000, int(getattr(config, "evals_max_trace_chars", 20000)))
