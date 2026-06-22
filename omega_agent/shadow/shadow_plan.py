from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from omega_agent.security.policy_rules import classify_action
from omega_agent.security.redaction import redact
from omega_agent.security.risk import score_risk


@dataclass(frozen=True)
class ShadowPlanStep:
    index: int
    name: str
    type: str
    tool_name: str | None
    arguments: dict[str, Any]
    action_category: str
    risk_level: str
    simulable: bool = True

    def as_api(self) -> dict[str, Any]:
        return redact(self.__dict__)


def build_plan(objective: str, *, source_type: str = "manual_plan", workflow_definition: dict[str, Any] | None = None) -> dict[str, Any]:
    if source_type == "workflow" and workflow_definition:
        steps = _workflow_steps(workflow_definition)
    else:
        steps = _objective_steps(objective)
    return redact(
        {
            "version": "shadow-plan.v1",
            "objective": objective,
            "source_type": source_type,
            "steps": [step.as_api() for step in steps],
            "invariants": [
                "real_workspace_unchanged",
                "no_external_write",
                "no_sensitive_path_copy",
                "live_promotion_rechecks_policy",
            ],
        }
    )


def _objective_steps(objective: str) -> list[ShadowPlanStep]:
    text = " ".join(str(objective or "").strip().split())
    lowered = text.lower()
    path = _extract_file_path(text)
    content = _extract_content(text)
    if path and any(token in lowered for token in ("crée", "cree", "create", "écris", "ecris", "write")):
        return [_tool_step(0, "Créer ou remplacer un fichier", "write_file", {"relative_path": path, "content": content})]
    if path and any(token in lowered for token in ("ajoute", "append")):
        return [_tool_step(0, "Ajouter du contenu au fichier", "append_file", {"relative_path": path, "content": content})]
    if path and any(token in lowered for token in ("supprime", "delete", "remove")):
        return [_tool_step(0, "Supprimer un fichier", "delete_file", {"relative_path": path})]
    shell = _extract_shell_command(text)
    if shell:
        return [_tool_step(0, "Exécuter une commande isolée", "run_shell", {"command": shell, "cwd": ".", "timeout_seconds": 60})]
    return [
        ShadowPlanStep(
            index=0,
            name="Étape manuelle non compilée",
            type="manual",
            tool_name=None,
            arguments={"objective": text},
            action_category="read_only",
            risk_level="medium",
            simulable=False,
        )
    ]


def _workflow_steps(definition: dict[str, Any]) -> list[ShadowPlanStep]:
    result: list[ShadowPlanStep] = []
    for index, step in enumerate(definition.get("steps") or []):
        step_type = str(step.get("type") or "")
        if step_type == "tool":
            result.append(_tool_step(index, str(step.get("name") or step.get("id") or f"Step {index + 1}"), str(step.get("tool") or ""), dict(step.get("arguments") or {})))
        elif step_type == "shell":
            result.append(
                _tool_step(
                    index,
                    str(step.get("name") or step.get("id") or f"Step {index + 1}"),
                    "run_shell",
                    {
                        "command": str(step.get("command") or ""),
                        "cwd": str(step.get("cwd") or "."),
                        "timeout_seconds": int(step.get("timeout_seconds") or 60),
                    },
                )
            )
        else:
            result.append(
                ShadowPlanStep(
                    index=index,
                    name=str(step.get("name") or step.get("id") or f"Step {index + 1}"),
                    type=step_type or "manual",
                    tool_name=None,
                    arguments=redact(dict(step)),
                    action_category="read_only",
                    risk_level=str(step.get("risk_level") or "low"),
                    simulable=step_type in {"condition", "wait", "final", "approval"},
                )
            )
    return result


def _tool_step(index: int, name: str, tool_name: str, arguments: dict[str, Any]) -> ShadowPlanStep:
    category = classify_action(tool_name, arguments)
    risk = score_risk(tool_name, arguments).level
    return ShadowPlanStep(index, name, "tool", tool_name, redact(arguments), category, risk, True)


def _extract_file_path(text: str) -> str | None:
    patterns = (
        r"(?:fichier|file)\s+[\"']?([A-Za-z0-9_.\-/\\]+)[\"']?",
        r"(?:crée|cree|create|write|écris|ecris|append|supprime|delete)\s+[\"']?([A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9_-]+)[\"']?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).replace("\\", "/").strip()
    return None


def _extract_content(text: str) -> str:
    match = re.search(r"(?:avec|with|contenant|containing|contenu)\s+[\"']?(.+?)[\"']?$", text, flags=re.IGNORECASE)
    return (match.group(1).strip().strip("\"'") if match else "OK") + ("\n" if not (match and match.group(1).endswith("\n")) else "")


def _extract_shell_command(text: str) -> str | None:
    match = re.search(r"(?:commande|command)\s+[\"'](.+)[\"']$", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None
