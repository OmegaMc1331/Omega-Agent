from __future__ import annotations

RUN_STATUSES = {"pending", "running", "paused", "succeeded", "failed", "cancelled", "needs_approval"}
ACTIVE_RUN_STATUSES = {"pending", "running", "paused", "needs_approval"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}

STEP_TYPES = {
    "reasoning",
    "tool_call",
    "approval",
    "observation",
    "checkpoint",
    "rollback",
    "final_response",
    "error",
    "provider_call",
}
STEP_STATUSES = {"pending", "running", "succeeded", "failed", "skipped"}

ACTION_STATUSES = {
    "planned",
    "allowed",
    "denied",
    "approval_required",
    "running",
    "succeeded",
    "failed",
    "rolled_back",
}


def validate_run_status(status: str) -> str:
    if status not in RUN_STATUSES:
        raise ValueError(f"Run status invalide: {status}")
    return status


def validate_step_type(step_type: str) -> str:
    if step_type not in STEP_TYPES:
        raise ValueError(f"Step type invalide: {step_type}")
    return step_type


def validate_step_status(status: str) -> str:
    if status not in STEP_STATUSES:
        raise ValueError(f"Step status invalide: {status}")
    return status


def validate_action_status(status: str) -> str:
    if status not in ACTION_STATUSES:
        raise ValueError(f"Action status invalide: {status}")
    return status
