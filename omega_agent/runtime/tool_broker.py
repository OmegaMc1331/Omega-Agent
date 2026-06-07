from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.multi_agent import MultiAgentRuntime
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.reasoning import emit_reasoning_event
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tools_registry import HANDLERS, ToolsRegistry
from omega_agent.security import log_action, workspace_policy_decision
from omega_agent.security.browser_policy import browser_action_requires_approval, validate_browser_tool_request
from omega_agent.security.desktop_policy import desktop_action_requires_approval, validate_desktop_tool_request
from omega_agent.security.project_policy import project_config, validate_project_tool
from omega_agent.tools.desktop import active_window_title


@dataclass(frozen=True)
class ToolResult:
    status: str
    output: str
    approval_id: str | None = None


class ToolBroker:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.registry = ToolsRegistry(config)
        self.approvals = ApprovalsStore(config)
        self.events = EventsStore(config)
        self.projects = ProjectsStore(config)
        self.agent_profiles = AgentProfilesStore(config)
        self.sessions = SessionsStore(config)
        self.multi_agent = MultiAgentRuntime(config)

    def call(self, tool_id: str, arguments: dict, session_id: str | None = None, approval_id: str | None = None) -> ToolResult:
        tool = self.registry.get(tool_id)
        if tool is None or not tool.enabled:
            return ToolResult("denied", "Tool introuvable ou desactive.")
        emit_reasoning_event(
            session_id or "",
            "reasoning.tool_considered",
            "Tool considéré",
            f"Omega évalue l'utilisation de {tool_id}.",
            status="completed",
            metadata={"tool_name": tool_id, "risk_level": tool.risk_level or tool.risk, "arguments": arguments},
            config=self.config,
        )
        emit_reasoning_event(
            session_id or "",
            "reasoning.tool_requested",
            "Tool demandé",
            f"{tool_id} est nécessaire pour traiter une étape de la demande.",
            status="running",
            metadata={"tool_name": tool_id, "risk_level": tool.risk_level or tool.risk},
            config=self.config,
        )
        try:
            profile = self.agent_profiles.profile_for_session(session_id)
            if profile.allowed_tools and tool_id not in profile.allowed_tools:
                raise PermissionError(f"Tool non autorise par le profil agent: {tool_id}")
            project = self.projects.project_for_session(session_id)
            project_policy = project.policy
            if self.config.workspace_full_access and not _path_inside_workspace(self.config.workspace, Path(project.root_path)):
                raise PermissionError("Projet hors OMEGA_WORKSPACE refuse en Workspace Full Access.")
            validate_project_tool(tool_id, arguments, project.root_path, project_policy, self.config)
            active_config = project_config(self.config, project.root_path, project_policy, tool_id=tool_id)
            validate_browser_tool_request(active_config, tool_id, arguments)
            validate_desktop_tool_request(active_config, tool_id, arguments, active_window_title())
        except (PermissionError, ValueError) as exc:
            log_action(self.config, "tool_denied", {"tool": tool_id, "reason": str(exc), "session_id": session_id})
            emit_reasoning_event(
                session_id or "",
                "reasoning.error",
                "Tool bloqué",
                str(exc),
                status="failed",
                metadata={"tool_name": tool_id},
                config=self.config,
            )
            return ToolResult("denied", str(exc))
        profile_requires_approval = _profile_requires_approval(profile, tool_id)
        session_policy_requires_approval = _session_requires_approval(self.sessions.get_session(session_id), tool.risk_level or tool.risk)
        browser_requires_approval = (
            tool_id.startswith("browser_")
            and active_config.browser_require_approval
            and (tool.requires_approval or browser_action_requires_approval(tool_id, arguments))
        )
        desktop_requires_approval = (
            tool_id.startswith("desktop_")
            and active_config.desktop_require_approval
            and (tool.requires_approval or desktop_action_requires_approval(tool_id))
        )
        require_approval = (tool.requires_approval and active_config.require_approval) or browser_requires_approval or desktop_requires_approval or profile_requires_approval or session_policy_requires_approval
        if active_config.workspace_full_access and tool_id in {"write_file", "delete_file", "create_directory", "delete_directory", "move_file", "copy_file", "list_tree", "run_shell", "git_add", "git_commit"}:
            require_approval = False
        decision = workspace_policy_decision(active_config, tool_id, arguments, require_approval=require_approval and approval_id is None)
        if decision.action == "deny":
            log_action(self.config, "tool_denied", {"tool": tool_id, "reason": decision.reason})
            emit_reasoning_event(
                session_id or "",
                "reasoning.error",
                "Tool refusé",
                decision.reason,
                status="failed",
                metadata={"tool_name": tool_id, "risk_level": decision.risk_level},
                config=self.config,
            )
            return ToolResult("denied", decision.reason)
        if decision.action == "require_approval" and require_approval:
            approval_risk = "critical" if profile.policy.get("approval_mode") == "critical" else decision.risk_level
            approval = self.approvals.create(tool_id, arguments, risk=approval_risk, session_id=session_id, reason=decision.reason)
            emit_reasoning_event(
                session_id or "",
                "reasoning.approval_required",
                "Approval requise",
                f"{tool_id} est bloqué jusqu'à validation utilisateur.",
                status="pending",
                metadata={"approval_id": approval.id, "tool_name": tool_id, "risk_level": approval_risk, "reason": decision.reason},
                config=self.config,
            )
            return ToolResult("approval_required", "Approval requise.", approval_id=approval.id)
        handler = HANDLERS.get(tool_id)
        if tool_id == "delegate_to_agent":
            try:
                delegation = self.multi_agent.delegate(
                    session_id or "",
                    str(arguments.get("child_agent_id") or ""),
                    str(arguments.get("task") or ""),
                    parent_agent_id=profile.id,
                    max_steps=int(arguments.get("max_steps") or 8),
                    allowed_tools=list(arguments.get("allowed_tools") or []),
                    run_now=True,
                )
            except Exception as exc:
                return ToolResult("denied", str(exc))
            return ToolResult("completed", delegation.result or f"Delegation creee: {delegation.id}")
        if handler is None:
            return ToolResult("denied", "Handler tool introuvable.")
        self.events.add("tool.started", {"tool_name": tool_id}, session_id=session_id)
        emit_reasoning_event(
            session_id or "",
            "reasoning.tool_started",
            "Tool démarré",
            f"Exécution de {tool_id}.",
            status="running",
            metadata={"tool_name": tool_id, "risk_level": tool.risk_level or tool.risk},
            config=self.config,
        )
        if tool_id.startswith("browser_"):
            self.events.add("browser.action.started", {"tool_name": tool_id}, session_id=session_id)
        if tool_id.startswith("desktop_"):
            self.events.add("desktop.action.started", {"tool_name": tool_id, "visible_control": True}, session_id=session_id)
        try:
            output = handler(active_config, arguments)
        except Exception as exc:
            if tool_id.startswith("browser_"):
                self.events.add("browser.error", {"tool_name": tool_id, "reason": str(exc)}, session_id=session_id)
            if tool_id.startswith("desktop_"):
                self.events.add("desktop.error", {"tool_name": tool_id, "reason": str(exc)}, session_id=session_id)
            log_action(self.config, "tool_denied", {"tool": tool_id, "reason": str(exc), "session_id": session_id})
            emit_reasoning_event(
                session_id or "",
                "reasoning.error",
                "Tool en échec",
                str(exc),
                status="failed",
                metadata={"tool_name": tool_id},
                config=self.config,
            )
            return ToolResult("denied", str(exc))
        self.events.add("tool.completed", {"tool_name": tool_id}, session_id=session_id)
        emit_reasoning_event(
            session_id or "",
            "reasoning.tool_completed",
            "Tool terminé",
            f"{tool_id} a terminé son exécution.",
            status="completed",
            metadata={"tool_name": tool_id},
            config=self.config,
        )
        emit_reasoning_event(
            session_id or "",
            "reasoning.observation",
            "Observation",
            _summarize_tool_output(output),
            status="completed",
            metadata={"tool_name": tool_id, "output_length": len(str(output))},
            config=self.config,
        )
        if tool_id.startswith("browser_"):
            self.events.add("browser.action.completed", {"tool_name": tool_id}, session_id=session_id)
        if tool_id.startswith("desktop_"):
            self.events.add("desktop.action.completed", {"tool_name": tool_id, "visible_control": True}, session_id=session_id)
        log_action(self.config, "tool_completed", {"tool": tool_id})
        return ToolResult("completed", output)


def _profile_requires_approval(profile, tool_id: str) -> bool:
    policy = profile.policy
    if policy.get("approval_mode") == "critical":
        return True
    if policy.get("all_sensitive_requires_approval") and tool_id in {"write_file", "run_shell", "git_diff"}:
        return True
    return tool_id in set(policy.get("require_approval_tools") or [])


def _summarize_tool_output(output: object) -> str:
    text = str(output or "").strip()
    if not text:
        return "Le tool n'a pas renvoyé de contenu."
    first_line = text.splitlines()[0][:500]
    suffix = "..." if len(text) > len(first_line) else ""
    return f"Sortie résumée: {first_line}{suffix}"


def _session_requires_approval(session, risk_level: str) -> bool:
    if session is None:
        return False
    try:
        metadata = json.loads(session.metadata_json)
    except json.JSONDecodeError:
        metadata = {}
    if not (metadata.get("external_channel") or metadata.get("untrusted_input") or metadata.get("scheduled_task") or metadata.get("scheduled")):
        return False
    return risk_level in {"high", "critical"}


def _path_inside_workspace(workspace: Path, candidate: Path) -> bool:
    workspace_resolved = workspace.resolve()
    candidate_resolved = candidate.expanduser().resolve()
    try:
        return os.path.commonpath([str(workspace_resolved), str(candidate_resolved)]) == str(workspace_resolved)
    except ValueError:
        return False
