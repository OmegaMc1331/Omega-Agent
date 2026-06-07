from __future__ import annotations

import json
from dataclasses import replace

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.delegation import Delegation, DelegationsStore
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.security import log_action

MAX_DELEGATION_DEPTH = 2
DEFAULT_MAX_STEPS = 8


class MultiAgentRuntime:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.delegations = DelegationsStore(config)
        self.agent_profiles = AgentProfilesStore(config)
        self.sessions = SessionsStore(config)
        self.projects = ProjectsStore(config)
        self.events = EventsStore(config)

    def delegate(
        self,
        session_id: str,
        child_agent_id: str,
        task: str,
        parent_agent_id: str | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        allowed_tools: list[str] | None = None,
        depth: int | None = None,
        run_now: bool = True,
    ) -> Delegation:
        session = self.sessions.get_session(session_id)
        if session is None:
            raise ValueError("Session introuvable.")
        parent_id = parent_agent_id or session.active_agent_profile_id or "omega-core"
        parent = self.agent_profiles.get(parent_id)
        child = self.agent_profiles.get(child_agent_id)
        if parent is None:
            raise PermissionError("Profil parent introuvable ou desactive.")
        if child is None:
            raise PermissionError("Profil enfant introuvable ou desactive.")

        current_depth = self.delegations.depth_for_session(session_id) if depth is None else depth
        if current_depth >= MAX_DELEGATION_DEPTH:
            raise PermissionError("Profondeur maximale de delegation atteinte.")
        inherited_tools = _intersect_tools(parent.allowed_tools, child.allowed_tools, allowed_tools or [])
        project = self.projects.project_for_session(session_id)
        inherited_policy = {
            "max_depth": MAX_DELEGATION_DEPTH,
            "depth": current_depth + 1,
            "max_steps": min(int(max_steps or DEFAULT_MAX_STEPS), DEFAULT_MAX_STEPS),
            "allowed_tools": inherited_tools,
            "project_id": project.id,
            "project_root": project.root_path,
        }
        delegation = self.delegations.create(
            session_id,
            parent.id,
            child.id,
            task,
            metadata={
                "depth": current_depth + 1,
                "max_steps": inherited_policy["max_steps"],
                "allowed_tools": inherited_tools,
                "inherited_policy": inherited_policy,
            },
        )
        self.events.add("delegation.created", {"delegation_id": delegation.id, "child_agent_id": child.id}, session_id=session_id)
        if run_now:
            return self.run(delegation.id)
        return delegation

    def run(self, delegation_id: str) -> Delegation:
        delegation = self.delegations.get(delegation_id)
        if delegation is None:
            raise ValueError("Delegation introuvable.")
        if delegation.status == "cancelled":
            return delegation
        self.delegations.update_status(delegation.id, "running")
        self.events.add("delegation.started", {"delegation_id": delegation.id, "child_agent_id": delegation.child_agent_id}, session_id=delegation.session_id)
        try:
            child = self.agent_profiles.get(delegation.child_agent_id)
            if child is None:
                raise PermissionError("Profil enfant introuvable ou desactive.")
            metadata = delegation.metadata
            allowed_tools = metadata.get("allowed_tools") or []
            limited_child = replace(child, allowed_tools_json=json.dumps(allowed_tools, ensure_ascii=False))
            context = build_context(self.config, delegation.session_id, query=delegation.task, agent_profile=limited_child)
            result = _summarize_delegation_result(delegation, context, allowed_tools)
            updated = self.delegations.update_status(delegation.id, "completed", result=result)
            self.sessions.add_message(
                delegation.session_id,
                "assistant",
                f"Delegation {delegation.child_agent_id} terminee:\n{result}",
                metadata={"delegation_id": delegation.id, "child_agent_id": delegation.child_agent_id},
            )
            self.events.add("delegation.completed", {"delegation_id": delegation.id, "child_agent_id": delegation.child_agent_id}, session_id=delegation.session_id)
            log_action(self.config, "delegation_completed", {"delegation_id": delegation.id})
            return updated
        except Exception as exc:
            updated = self.delegations.update_status(delegation.id, "failed", result=str(exc))
            self.events.add("delegation.failed", {"delegation_id": delegation.id, "reason": str(exc)}, session_id=delegation.session_id)
            log_action(self.config, "delegation_failed", {"delegation_id": delegation.id, "reason": str(exc)})
            return updated


def _intersect_tools(parent_tools: list[str], child_tools: list[str], requested_tools: list[str]) -> list[str]:
    parent = set(parent_tools)
    child = set(child_tools)
    if not parent:
        parent = child
    allowed = parent.intersection(child)
    if requested_tools:
        allowed = allowed.intersection(set(requested_tools))
    return sorted(allowed)


def _summarize_delegation_result(delegation: Delegation, context: dict, allowed_tools: list[str]) -> str:
    payload = {
        "task": delegation.task,
        "child_agent": delegation.child_agent_id,
        "max_steps": delegation.metadata.get("max_steps", DEFAULT_MAX_STEPS),
        "allowed_tools": allowed_tools,
        "visible_skills": [skill.get("id") for skill in context.get("skills", [])],
        "note": "Delegation executee en contexte limite; les actions sensibles restent soumises aux approvals normales.",
    }
    return json.dumps(payload, ensure_ascii=False)
