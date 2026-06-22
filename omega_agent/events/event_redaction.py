from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from omega_agent.events.protocol import OmegaEvent
from omega_agent.security.redaction import redact

DEFAULT_MAX_TRACE_CHARS = 20000


def redact_event(event: OmegaEvent, *, max_chars: int = DEFAULT_MAX_TRACE_CHARS) -> OmegaEvent:
    payload = truncate_value(redact(event.payload), max_chars=max_chars)
    metadata = truncate_value(redact(event.metadata), max_chars=max_chars)
    return replace(event, payload=_as_dict(payload), metadata=_as_dict(metadata))


def event_for_ui(event: OmegaEvent, *, max_chars: int = DEFAULT_MAX_TRACE_CHARS) -> OmegaEvent | None:
    if event.visibility == "internal":
        return None
    return redact_event(event, max_chars=max_chars)


def truncate_value(value: Any, *, max_chars: int = DEFAULT_MAX_TRACE_CHARS) -> Any:
    if max_chars <= 0:
        max_chars = DEFAULT_MAX_TRACE_CHARS
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "...[TRUNCATED]"
    if isinstance(value, dict):
        result = {str(key): truncate_value(item, max_chars=max_chars) for key, item in value.items()}
        return _truncate_container(result, max_chars=max_chars)
    if isinstance(value, list):
        result = [truncate_value(item, max_chars=max_chars) for item in value]
        return _truncate_container(result, max_chars=max_chars)
    return value


def _truncate_container(value: Any, *, max_chars: int) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)[:max_chars]
    if len(encoded) <= max_chars:
        return value
    return {"truncated": True, "preview": encoded[:max_chars] + "...[TRUNCATED]"}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {"value": value}
