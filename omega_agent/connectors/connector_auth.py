from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.connectors.base import Connector, ConnectorAuthStatus


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_auth_status(connector: Connector | dict[str, Any]) -> str:
    auth_type = _get(connector, "auth_type", "none")
    auth_ref = _get(connector, "auth_ref", None)
    if auth_type == "none" or not auth_ref:
        return "none"
    value = os.getenv(str(auth_ref), "")
    if value.strip():
        return "configured"
    return "missing"


def auth_status_record(connector: Connector | dict[str, Any]) -> ConnectorAuthStatus:
    return ConnectorAuthStatus(
        id=str(uuid4()),
        connector_id=str(_get(connector, "id", "")),
        status=compute_auth_status(connector),
        auth_type=str(_get(connector, "auth_type", "none")),
        auth_ref=_get(connector, "auth_ref", None),
        last_checked_at=now_iso(),
        metadata={},
    )


def _get(value: Connector | dict[str, Any], key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
