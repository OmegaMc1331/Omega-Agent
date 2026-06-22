from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from omega_agent.security.redaction import redact

CANDIDATE_STATUSES = {"pending", "accepted", "rejected", "promoted", "archived"}
SKILL_STATUSES = {"draft", "active", "disabled", "archived"}
SKILL_TYPES = {"prompt", "workflow", "tool_recipe", "code_agent_recipe", "research_recipe"}
TEST_STATUSES = {"passed", "failed", "error"}


def parse_json(value: str | None, default):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


@dataclass(frozen=True)
class SkillCandidate:
    id: str
    title: str
    description: str
    source_run_ids: list[str]
    source_workflow_ids: list[str]
    detected_pattern: dict[str, Any]
    proposed_skill: dict[str, Any]
    confidence: float
    status: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class StoredSkill:
    id: str
    name: str
    slug: str
    description: str
    version: str
    status: str
    skill_type: str
    definition: dict[str, Any]
    test_cases: list[dict[str, Any]]
    source_candidate_id: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any]
    risk_level: str = "low"
    enabled: bool = False
    allowed_tools: list[str] | None = None

    def as_api(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_tools"] = list(self.allowed_tools or [])
        return redact(payload)


@dataclass(frozen=True)
class SkillVersion:
    id: str
    skill_id: str
    version: str
    definition: dict[str, Any]
    changelog: str
    created_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class SkillTestRun:
    id: str
    skill_id: str
    version: str
    status: str
    results: dict[str, Any]
    created_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class SkillUsageEvent:
    id: str
    skill_id: str
    run_id: str | None
    status: str
    success: bool | None
    duration_ms: int | None
    created_at: str
    metadata: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))
