from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]
SessionStatus = Literal["active", "archived", "closed"]
JobKind = Literal["summarize_session", "scan_workspace", "compact_memory", "memory_compaction", "run_scheduled_prompt", "project_health_check"]
MemoryScope = Literal["global", "session", "project", "agent", "run"]
StandingOrderScope = Literal["global", "session", "project"]
ChannelType = Literal["web", "cli", "webhook", "telegram", "discord"]
ScheduleType = Literal["once", "interval", "cron"]
ReasoningStatus = Literal["pending", "running", "completed", "failed"]
ReasoningVisibility = Literal["public", "internal", "redacted"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = Field(default=None, max_length=64)
    thinking_level: str | None = Field(default=None, min_length=2, max_length=16)


class SessionCreateRequest(BaseModel):
    title: str = Field(default="Nouvelle session", min_length=1, max_length=160)


class SessionRenameRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: SessionStatus | None = None
    metadata: dict = Field(default_factory=dict)


class SessionProjectRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=64)


class SessionAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)


class AgentCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    system_prompt: str = Field(default="", max_length=50000)
    enabled: bool = True
    allowed_tools: list[str] = Field(default_factory=list, max_length=64)
    allowed_skills: list[str] = Field(default_factory=list, max_length=64)
    risk_level: RiskLevel = "low"
    policy: dict = Field(default_factory=dict)


class AgentPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=50000)
    enabled: bool | None = None
    allowed_tools: list[str] | None = Field(default=None, max_length=64)
    allowed_skills: list[str] | None = Field(default=None, max_length=64)
    risk_level: RiskLevel | None = None
    policy: dict | None = None


class ChannelCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    type: ChannelType
    name: str = Field(min_length=1, max_length=160)
    enabled: bool = False
    config: dict = Field(default_factory=dict)


class ChannelPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    config: dict | None = None


class WebhookMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    external_account_id: str = Field(default="local", max_length=200)
    display_name: str = Field(default="", max_length=200)
    route_to_agent: str | None = Field(default=None, max_length=64)
    metadata: dict = Field(default_factory=dict)


class ScheduledTaskCreateRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    prompt: str = Field(min_length=1, max_length=20000)
    schedule_type: ScheduleType = "once"
    schedule_value: str = Field(default="", max_length=200)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class ScheduledTaskPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    prompt: str | None = Field(default=None, min_length=1, max_length=20000)
    schedule_type: ScheduleType | None = None
    schedule_value: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None
    metadata: dict | None = None


class StandingOrderCreateRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    content: str = Field(min_length=1, max_length=20000)
    scope: StandingOrderScope = "global"
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)


class StandingOrderPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    scope: StandingOrderScope | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)


class DelegationCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    child_agent_id: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=20000)
    parent_agent_id: str | None = Field(default=None, max_length=64)
    max_steps: int = Field(default=8, ge=1, le=8)
    allowed_tools: list[str] = Field(default_factory=list, max_length=64)
    run_now: bool = True


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    root_path: str = Field(min_length=1, max_length=1000)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    policy: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    root_path: str | None = Field(default=None, min_length=1, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    policy: dict | None = None
    metadata: dict | None = None


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    description: str = Field(default="", max_length=1000)
    instructions: str = Field(default="", max_length=50000)
    tools: list[str] = Field(default_factory=list, max_length=32)
    risk: RiskLevel = "low"
    tags: list[str] = Field(default_factory=list, max_length=32)
    skill_type: str | None = None
    definition: dict | None = None
    test_cases: list[dict] = Field(default_factory=list, max_length=50)
    metadata: dict = Field(default_factory=dict)


class SkillUpdateRequest(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    skill_type: str | None = None
    definition: dict | None = None
    test_cases: list[dict] | None = Field(default=None, max_length=50)
    changelog: str = Field(default="Skill updated", max_length=1000)


class PluginUpdateRequest(BaseModel):
    enabled: bool


class PluginEnableRequest(BaseModel):
    confirmed: bool = False


class ToolUpdateRequest(BaseModel):
    enabled: bool


class JobCreateRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    kind: JobKind
    input: dict = Field(default_factory=dict)


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    key: str = Field(default="", max_length=160)
    scope: MemoryScope = "global"
    tags: list[str] = Field(default_factory=list, max_length=32)


class SettingsPatchRequest(BaseModel):
    values: dict = Field(default_factory=dict)


class ConfigPatchRequest(BaseModel):
    values: dict = Field(default_factory=dict)


class ResearchStartRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=160)
    session_id: str | None = Field(default=None, max_length=64)
    manual_sources: list[dict] = Field(default_factory=list, max_length=20)


class ResearchExportRequest(BaseModel):
    format: Literal["markdown", "json"] = "markdown"


class StatusResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    workspace: str
    version: str
    auth_codex: dict
    gateway: dict
    login_hint: str | None = None


class ReasoningEventResponse(BaseModel):
    id: str
    session_id: str
    message_id: str | None = None
    type: str
    title: str
    content: str
    status: ReasoningStatus
    visibility: ReasoningVisibility
    created_at: str
    metadata_json: str = "{}"
    metadata: dict = Field(default_factory=dict)
