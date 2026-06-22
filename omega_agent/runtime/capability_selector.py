from __future__ import annotations

import re
from dataclasses import asdict

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.capabilities import CapabilitiesRegistry, Capability
from omega_agent.runtime.capability_policy import CapabilityPolicy, risk_rank
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.security.redaction import redact


class CapabilitySelector:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.registry = CapabilitiesRegistry(config)
        self.policy = CapabilityPolicy(config)
        self.agent_profiles = AgentProfilesStore(config)
        self.projects = ProjectsStore(config)

    def select_capabilities_for_task(
        self,
        message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        agent_profile_id: str | None = None,
    ) -> list[Capability]:
        limit = max(1, int(self.config.capabilities_max_in_context or 20))
        profile = self.agent_profiles.get(agent_profile_id) if agent_profile_id else self.agent_profiles.profile_for_session(session_id)
        project_scopes = self._project_scopes(project_id, session_id)
        candidates = []
        for capability in self.registry.list():
            decision = self.policy.is_allowed_for_context(capability, agent_profile=profile, project_scopes=project_scopes)
            if not decision.allowed:
                continue
            score = _score(message, capability)
            if score <= 0 and capability.type in {"plugin", "mcp_server", "a2a_agent", "channel", "connector_operation"}:
                continue
            candidates.append((score, risk_rank(capability.risk_level), capability.name.lower(), capability))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[3] for item in candidates[:limit]]

    def compact_for_prompt(
        self,
        message: str,
        session_id: str | None = None,
        project_id: str | None = None,
        agent_profile_id: str | None = None,
    ) -> list[dict]:
        return [_compact(item) for item in self.select_capabilities_for_task(message, session_id, project_id, agent_profile_id)]

    def _project_scopes(self, project_id: str | None, session_id: str | None) -> set[str]:
        if project_id:
            project = self.projects.get(project_id)
        else:
            project = self.projects.project_for_session(session_id)
        scopes = {"workspace", "session", "model", "provider"}
        if project and project.enabled:
            scopes.add("project")
            for tool_id in project.policy.allowed_tools:
                if tool_id.startswith("git_"):
                    scopes.add("git")
                if "file" in tool_id or tool_id in {"list_tree", "create_directory", "delete_directory"}:
                    scopes.add("filesystem")
                if tool_id == "run_shell":
                    scopes.add("shell")
        return scopes


def _compact(capability: Capability) -> dict:
    return redact(
        {
            "id": capability.id,
            "name": capability.name,
            "type": capability.type,
            "description": capability.description[:220],
            "risk_level": capability.risk_level,
            "requires_approval": capability.requires_approval_default,
            "scopes": capability.scopes[:5],
            "auth_status": capability.auth_status,
        }
    )


def _score(message: str, capability: Capability) -> int:
    normalized = _normalize(message)
    haystack = _normalize(
        " ".join(
            [
                capability.id,
                capability.name,
                capability.description,
                capability.type,
                " ".join(capability.tags),
                " ".join(capability.scopes),
            ]
        )
    )
    tokens = [token for token in re.split(r"\W+", normalized) if len(token) > 2]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 2
    for keyword, capability_terms in INTENT_HINTS.items():
        if keyword in normalized and any(term in haystack for term in capability_terms):
            score += 8
    if capability.type == "tool" and capability.risk_level == "low":
        score += 1
    if capability.type == "connector_operation":
        if any(term in normalized for term in ["api", "openapi", "connecteur", "connector", "github", "http", "endpoint"]):
            score += 5
        if "browser" in normalized or "navigateur" in normalized:
            score += 2
    if capability.type == "provider" and any(term in normalized for term in ["modele", "model", "provider", "llm"]):
        score += 6
    return score


def _normalize(value: str) -> str:
    import unicodedata

    lowered = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in lowered if not unicodedata.combining(char))


INTENT_HINTS = {
    "fichier": ["filesystem", "file", "workspace"],
    "file": ["filesystem", "file", "workspace"],
    "cree": ["write", "filesystem", "file"],
    "create": ["write", "filesystem", "file"],
    "modifie": ["write", "filesystem", "file"],
    "ecris": ["write", "filesystem", "file"],
    "supprime": ["delete", "filesystem", "file"],
    "delete": ["delete", "filesystem", "file"],
    "commande": ["shell", "run_shell"],
    "shell": ["shell", "run_shell"],
    "pytest": ["shell", "run_shell"],
    "npm": ["shell", "run_shell"],
    "git": ["git"],
    "memoire": ["memory", "remember", "recall"],
    "memory": ["memory", "remember", "recall"],
    "navigateur": ["browser"],
    "browser": ["browser"],
    "desktop": ["desktop"],
    "skill": ["skill"],
    "plugin": ["plugin"],
    "mcp": ["mcp"],
    "a2a": ["a2a"],
    "api": ["connector", "api", "openapi", "http"],
    "openapi": ["connector", "api", "openapi"],
    "connecteur": ["connector", "api"],
    "connector": ["connector", "api"],
    "github": ["github", "connector"],
    "issue": ["github", "connector"],
    "endpoint": ["http", "api", "connector"],
}
