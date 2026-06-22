from __future__ import annotations

from typing import Any

from omega_agent.workflows.workflow_models import WORKFLOW_ERROR_MODES, WORKFLOW_STEP_TYPES


class WorkflowValidationError(ValueError):
    pass


def validate_workflow(definition: dict[str, Any], *, max_steps: int = 30, allow_nested_workflows: bool = False) -> dict[str, Any]:
    if not isinstance(definition, dict):
        raise WorkflowValidationError("Workflow definition must be a JSON object.")
    name = str(definition.get("name") or "").strip()
    if not name:
        raise WorkflowValidationError("Workflow name is required.")
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowValidationError("Workflow steps must be a non-empty list.")
    if len(steps) > max(1, int(max_steps or 30)):
        raise WorkflowValidationError(f"Workflow has too many steps. Maximum is {max_steps}.")

    seen_ids: set[str] = set()
    normalized_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            raise WorkflowValidationError(f"Step {index} must be an object.")
        step = dict(raw_step)
        step_type = str(step.get("type") or "").strip()
        if step_type not in WORKFLOW_STEP_TYPES:
            raise WorkflowValidationError(f"Unknown workflow step type: {step_type or '<missing>'}.")
        if step_type == "workflow" and not allow_nested_workflows:
            raise WorkflowValidationError("Nested workflows are disabled by configuration.")
        step_id = str(step.get("id") or f"step-{index + 1}").strip()
        if step_id in seen_ids:
            raise WorkflowValidationError(f"Duplicate workflow step id: {step_id}.")
        seen_ids.add(step_id)
        step["id"] = step_id
        step["name"] = str(step.get("name") or step_id).strip() or step_id
        step["on_error"] = str(step.get("on_error") or "fail").strip()
        if step["on_error"] not in WORKFLOW_ERROR_MODES:
            raise WorkflowValidationError(f"Invalid on_error for step {step_id}: {step['on_error']}.")
        step["retries"] = max(0, int(step.get("retries") or 0))
        _validate_step(step)
        normalized_steps.append(step)

    normalized = dict(definition)
    normalized["name"] = name
    normalized["description"] = str(definition.get("description") or "")
    normalized["version"] = str(definition.get("version") or "1.0")
    normalized["inputs"] = definition.get("inputs") if isinstance(definition.get("inputs"), dict) else {}
    normalized["steps"] = normalized_steps
    return normalized


def _validate_step(step: dict[str, Any]) -> None:
    step_type = step["type"]
    step_id = step["id"]
    if step_type == "tool":
        if not str(step.get("tool") or "").strip():
            raise WorkflowValidationError(f"Tool step {step_id} requires a tool field.")
        if "arguments" not in step:
            step["arguments"] = {}
        if not isinstance(step["arguments"], dict):
            raise WorkflowValidationError(f"Tool step {step_id} arguments must be an object.")
    elif step_type == "shell":
        if not str(step.get("command") or "").strip():
            raise WorkflowValidationError(f"Shell step {step_id} requires a command.")
    elif step_type == "approval":
        if not str(step.get("message") or "").strip():
            raise WorkflowValidationError(f"Approval step {step_id} requires a message.")
        step["required"] = bool(step.get("required", True))
    elif step_type == "condition":
        if not str(step.get("expression") or "").strip():
            raise WorkflowValidationError(f"Condition step {step_id} requires an expression.")
    elif step_type == "wait":
        step["seconds"] = max(0, int(step.get("seconds") or 0))
    elif step_type == "memory":
        if not str(step.get("operation") or "search").strip():
            raise WorkflowValidationError(f"Memory step {step_id} requires an operation.")
    elif step_type == "agent":
        if not str(step.get("prompt") or step.get("message") or "").strip():
            raise WorkflowValidationError(f"Agent step {step_id} requires a prompt.")
    elif step_type == "workflow":
        if not str(step.get("workflow_id") or "").strip():
            raise WorkflowValidationError(f"Nested workflow step {step_id} requires workflow_id.")
    elif step_type == "final":
        if not str(step.get("message") or "").strip():
            step["message"] = "Workflow completed."
