from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from omega_agent.security.redaction import redact

CONNECTOR_TYPES = {"builtin", "openapi", "local_http", "mcp", "github", "filesystem", "custom"}
TRUST_LEVELS = {"builtin", "local", "untrusted", "blocked"}
AUTH_TYPES = {"none", "env_secret", "oauth_stub", "token_stub"}
CONNECTOR_STATUSES = {"available", "missing_auth", "disabled", "error", "unknown"}
RISK_LEVELS = {"low", "medium", "high", "critical"}
ACTION_CATEGORIES = {"read_only", "reversible_write", "destructive_write", "external_side_effect", "system_sensitive"}


@dataclass(frozen=True)
class ConnectorOperation:
    id: str
    connector_id: str
    name: str
    description: str = ""
    method: str | None = None
    path: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    risk_level: str = "low"
    requires_approval_default: bool = False
    action_category: str = "read_only"
    enabled: bool = True

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class Connector:
    id: str
    type: str
    name: str
    description: str = ""
    enabled: bool = False
    trust_level: str = "untrusted"
    auth_type: str = "none"
    auth_ref: str | None = None
    base_url: str | None = None
    scopes: list[str] = field(default_factory=list)
    operations: list[ConnectorOperation] = field(default_factory=list)
    risk_level: str = "medium"
    status: str = "unknown"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operations_count"] = len(self.operations)
        redacted = redact(payload)
        redacted["auth_type"] = self.auth_type
        redacted["auth_ref"] = self.auth_ref
        return redacted


@dataclass(frozen=True)
class ConnectorUsageEvent:
    id: str
    connector_id: str
    operation_id: str | None
    run_id: str | None
    session_id: str | None
    status: str
    latency_ms: int | None
    error: str | None
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class ConnectorAuthStatus:
    id: str
    connector_id: str
    status: str
    auth_type: str
    auth_ref: str | None
    last_checked_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        redacted = redact(asdict(self))
        redacted["auth_type"] = self.auth_type
        redacted["auth_ref"] = self.auth_ref
        return redacted


def normalize_risk(value: str | None) -> str:
    lowered = str(value or "medium").strip().lower()
    return lowered if lowered in RISK_LEVELS else "medium"


def normalize_action_category(value: str | None) -> str:
    lowered = str(value or "read_only").strip().lower()
    return lowered if lowered in ACTION_CATEGORIES else "read_only"
