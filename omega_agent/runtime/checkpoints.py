from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact


def checkpoint_state(
    config: OmegaConfig,
    *,
    run_id: str,
    session_id: str,
    current_step: dict | None = None,
    active_agent_profile_id: str | None = None,
    project_id: str | None = None,
    model_ref: str | None = None,
    policy_context: dict | None = None,
    tool_observations: list[dict] | None = None,
    pending_approvals: list[dict] | None = None,
    memory_references: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    state = {
        "run_id": run_id,
        "session_id": session_id,
        "current_step": current_step or {},
        "active_agent_profile_id": active_agent_profile_id,
        "project_id": project_id,
        "model_ref": model_ref,
        "policy_context": policy_context or {
            "workspace": str(config.workspace),
            "workspace_full_access": config.workspace_full_access,
            "shell_full_access_in_workspace": config.shell_full_access_in_workspace,
            "allow_delete_in_workspace": config.allow_delete_in_workspace,
            "allow_git_write_in_workspace": config.allow_git_write_in_workspace,
        },
        "tool_observations": tool_observations or [],
        "pending_approvals": pending_approvals or [],
        "memory_references": memory_references or [],
        "timestamps": {"created_at": datetime.now(timezone.utc).isoformat()},
        "metadata": metadata or {},
    }
    return redact(state)


def sanitize_checkpoint_state(state: dict | None) -> dict:
    if not state:
        return {}
    sanitized = dict(state)
    sanitized.pop("system_prompt", None)
    sanitized.pop("prompt", None)
    sanitized.pop("messages", None)
    return redact(sanitized)
