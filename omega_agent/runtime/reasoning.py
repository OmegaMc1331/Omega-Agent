from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

ReasoningStatus = Literal["pending", "running", "completed", "failed"]
ReasoningVisibility = Literal["public", "internal", "redacted"]
ReasoningDetail = Literal["off", "minimal", "normal", "verbose"]

PUBLIC_VISIBILITIES = {"public", "redacted"}
VALID_DETAILS = {"off", "minimal", "normal", "verbose"}


@dataclass(frozen=True)
class ReasoningEvent:
    id: str
    session_id: str
    message_id: str | None
    type: str
    title: str
    content: str
    status: ReasoningStatus
    visibility: ReasoningVisibility
    created_at: str
    metadata_json: str = "{}"

    def as_api(self) -> dict:
        data = asdict(self)
        try:
            data["metadata"] = json.loads(self.metadata_json)
        except json.JSONDecodeError:
            data["metadata"] = {}
        return redact(data)


ReasoningSink = Callable[[ReasoningEvent], Awaitable[None] | None]


class ReasoningStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.init_db()

    def init_db(self) -> None:
        with connect_runtime_db(self.config):
            pass

    def add(
        self,
        session_id: str,
        event_type: str,
        title: str,
        content: str,
        status: ReasoningStatus = "running",
        visibility: ReasoningVisibility = "public",
        metadata: dict | None = None,
        message_id: str | None = None,
    ) -> ReasoningEvent:
        clean_metadata = redact(metadata or {})
        clean_content = redact(str(content or ""))
        clean_title = redact(str(title or event_type))
        event = ReasoningEvent(
            id=uuid4().hex,
            session_id=session_id,
            message_id=message_id,
            type=event_type,
            title=clean_title,
            content=clean_content,
            status=status,
            visibility=visibility,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata_json=json.dumps(clean_metadata, ensure_ascii=False),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO reasoning_events(
                    id, session_id, message_id, type, title, content, status,
                    visibility, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.session_id,
                    event.message_id,
                    event.type,
                    event.title,
                    event.content,
                    event.status,
                    event.visibility,
                    event.created_at,
                    event.metadata_json,
                ),
            )
        return event

    def list_for_session(self, session_id: str, include_internal: bool = False) -> list[ReasoningEvent]:
        query = """
            SELECT id, session_id, message_id, type, title, content, status,
                   visibility, created_at, metadata_json
            FROM reasoning_events
            WHERE session_id = ?
        """
        params: list[object] = [session_id]
        if not include_internal:
            query += " AND visibility IN ('public', 'redacted')"
        query += " ORDER BY created_at ASC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def list_for_message(self, message_id: str, include_internal: bool = False) -> list[ReasoningEvent]:
        query = """
            SELECT id, session_id, message_id, type, title, content, status,
                   visibility, created_at, metadata_json
            FROM reasoning_events
            WHERE message_id = ?
        """
        params: list[object] = [message_id]
        if not include_internal:
            query += " AND visibility IN ('public', 'redacted')"
        query += " ORDER BY created_at ASC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def _from_row(self, row) -> ReasoningEvent:
        return ReasoningEvent(
            id=row["id"],
            session_id=row["session_id"],
            message_id=row["message_id"],
            type=row["type"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            visibility=row["visibility"],
            created_at=row["created_at"],
            metadata_json=row["metadata_json"],
        )


def reasoning_enabled(config: OmegaConfig) -> bool:
    return config.reasoning_stream and config.reasoning_detail != "off"


def should_emit(config: OmegaConfig, event_type: str) -> bool:
    if not reasoning_enabled(config):
        return False
    detail = config.reasoning_detail
    if detail == "verbose":
        return True
    if detail == "normal":
        return True
    minimal_types = {
        "reasoning.started",
        "reasoning.plan",
        "reasoning.tool_started",
        "reasoning.tool_completed",
        "reasoning.approval_required",
        "reasoning.completed",
        "reasoning.error",
    }
    return event_type in minimal_types


def emit_reasoning_event(
    session_id,
    type,
    title,
    content,
    status="running",
    visibility="public",
    metadata=None,
    *,
    config: OmegaConfig | None = None,
    message_id: str | None = None,
    sink: ReasoningSink | None = None,
) -> ReasoningEvent | None:
    if not str(session_id or "").strip():
        return None
    if config is None or not should_emit(config, str(type)):
        return None
    event = ReasoningStore(config).add(
        str(session_id),
        str(type),
        str(title),
        str(content),
        status=status,
        visibility=visibility,
        metadata=metadata,
        message_id=message_id,
    )
    if sink is not None and event.visibility in PUBLIC_VISIBILITIES:
        result = sink(event)
        if inspect.isawaitable(result):
            raise RuntimeError("emit_reasoning_event received an async sink; use emit_reasoning_event_async instead.")
    return event


async def emit_reasoning_event_async(
    session_id: str,
    event_type: str,
    title: str,
    content: str,
    *,
    config: OmegaConfig,
    status: ReasoningStatus = "running",
    visibility: ReasoningVisibility = "public",
    metadata: dict | None = None,
    message_id: str | None = None,
    sink: ReasoningSink | None = None,
) -> ReasoningEvent | None:
    event = emit_reasoning_event(
        session_id,
        event_type,
        title,
        content,
        status=status,
        visibility=visibility,
        metadata=metadata,
        config=config,
        message_id=message_id,
    )
    if event is not None and sink is not None and event.visibility in PUBLIC_VISIBILITIES:
        result = sink(event)
        if inspect.isawaitable(result):
            await result
    return event


def reasoning_event_payload(event: ReasoningEvent) -> dict:
    return event.as_api()
