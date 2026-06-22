from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

EVENT_VERSION = "ag-ui.v1"

EVENT_DOMAINS = {
    "chat",
    "message",
    "run",
    "step",
    "reasoning",
    "tool",
    "approval",
    "policy",
    "snapshot",
    "rollback",
    "workflow",
    "memory",
    "eval",
    "connector",
    "model",
    "system",
    "self_healing",
    "action",
    "checkpoint",
    "replay",
    "research",
    "skill",
    "budget",
    "risk",
    "shadow",
}

EVENT_LEVELS = {"debug", "info", "warning", "error", "critical"}
EVENT_VISIBILITIES = {"public", "internal", "redacted"}
EVENT_SOURCES = {"gateway", "runtime", "tool", "policy", "model", "ui", "connector", "workflow", "system"}

KNOWN_EVENT_TYPES = {
    "chat.message.received",
    "message.created",
    "message.delta",
    "message.completed",
    "run.created",
    "run.started",
    "run.completed",
    "run.failed",
    "step.started",
    "step.completed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "approval.required",
    "approval.resolved",
    "policy.denied",
    "policy.allowed",
    "snapshot.created",
    "rollback.completed",
    "workflow.step.completed",
    "memory.created",
    "eval.case.failed",
    "connector.operation.completed",
    "self_healing.suggested",
    "research.started",
    "research.plan.created",
    "research.source.collected",
    "research.claim.extracted",
    "research.evidence.linked",
    "research.claim.verified",
    "research.report.created",
    "research.completed",
    "research.failed",
    "skill.candidate.detected",
    "skill.candidate.accepted",
    "skill.candidate.rejected",
    "skill.created",
    "skill.test.started",
    "skill.test.completed",
    "skill.activated",
    "skill.disabled",
    "skill.used",
    "budget.warning",
    "budget.exceeded",
    "budget.violation.created",
    "budget.run.paused",
    "budget.action.denied",
    "risk.blocked",
    "risk.approval_required",
    "shadow.created",
    "shadow.started",
    "shadow.step.started",
    "shadow.step.completed",
    "shadow.diff.created",
    "shadow.risk.created",
    "shadow.promoted",
    "shadow.rejected",
    "shadow.comparison.created",
}


@dataclass(frozen=True)
class OmegaEvent:
    id: str
    version: str
    type: str
    timestamp: str
    session_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    user_id: str | None = None
    source: str = "runtime"
    level: str = "info"
    visibility: str = "public"
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
        source: str = "runtime",
        level: str = "info",
        visibility: str = "public",
        metadata: dict[str, Any] | None = None,
    ) -> "OmegaEvent":
        event_payload = payload or {}
        return cls(
            id=uuid4().hex,
            version=EVENT_VERSION,
            type=normalize_event_type(event_type),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id or _optional_str(event_payload.get("session_id")),
            run_id=run_id or _optional_str(event_payload.get("run_id")),
            step_id=step_id or _optional_str(event_payload.get("step_id")),
            user_id=user_id,
            source=normalize_source(source or infer_source(event_type)),
            level=normalize_level(level or infer_level(event_type)),
            visibility=normalize_visibility(visibility),
            payload=dict(event_payload),
            metadata=dict(metadata or {}),
        )

    def as_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_id": self.id,
            "version": self.version,
            "type": self.type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "user_id": self.user_id,
            "source": self.source,
            "level": self.level,
            "visibility": self.visibility,
            "payload": self.payload,
            "metadata": self.metadata,
        }


def normalize_event_type(event_type: str) -> str:
    value = str(event_type or "system.event").strip().lower().replace("_", ".")
    if not value:
        return "system.event"
    if "." not in value:
        return f"system.{value}"
    return value


def normalize_source(source: str) -> str:
    value = str(source or "runtime").strip().lower()
    return value if value in EVENT_SOURCES else "runtime"


def normalize_level(level: str) -> str:
    value = str(level or "info").strip().lower()
    return value if value in EVENT_LEVELS else "info"


def normalize_visibility(visibility: str) -> str:
    value = str(visibility or "public").strip().lower()
    return value if value in EVENT_VISIBILITIES else "public"


def infer_source(event_type: str) -> str:
    domain = normalize_event_type(event_type).split(".", 1)[0]
    if domain in {"tool"}:
        return "tool"
    if domain in {"policy", "approval"}:
        return "policy"
    if domain == "connector":
        return "connector"
    if domain == "model":
        return "model"
    if domain == "workflow":
        return "workflow"
    if domain in {"chat", "message"}:
        return "gateway"
    if domain == "system":
        return "system"
    return "runtime"


def infer_level(event_type: str) -> str:
    value = normalize_event_type(event_type)
    if value.endswith(".failed") or value.endswith(".error"):
        return "error"
    if value.endswith(".denied") or value.endswith(".required"):
        return "warning"
    if value.endswith(".critical"):
        return "critical"
    return "info"


def event_type_catalog() -> list[str]:
    return sorted(KNOWN_EVENT_TYPES)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
