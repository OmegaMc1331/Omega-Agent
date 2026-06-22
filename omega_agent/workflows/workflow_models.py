from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from omega_agent.security.redaction import redact

WORKFLOW_STATUSES = {"pending", "running", "paused", "succeeded", "failed", "cancelled"}
WORKFLOW_STEP_STATUSES = {"pending", "running", "succeeded", "failed", "skipped", "waiting_approval"}
WORKFLOW_STEP_TYPES = {"tool", "agent", "approval", "condition", "wait", "shell", "memory", "workflow", "final"}
WORKFLOW_ERROR_MODES = {"fail", "retry", "continue", "ask_user"}


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    description: str
    version: str
    enabled: bool
    definition: dict[str, Any]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(self.__dict__)


@dataclass(frozen=True)
class WorkflowRun:
    id: str
    workflow_id: str
    run_id: str | None
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    current_step_index: int
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str
    error: str | None
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(self.__dict__)


@dataclass(frozen=True)
class WorkflowStepRun:
    id: str
    workflow_run_id: str
    step_id: str
    step_index: int
    name: str
    type: str
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    started_at: str | None
    completed_at: str | None
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(self.__dict__)


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    name: str
    description: str
    category: str
    definition: dict[str, Any]
    created_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(self.__dict__)


def parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
