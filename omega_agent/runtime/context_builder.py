from __future__ import annotations

from dataclasses import asdict

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfile, AgentProfilesStore, filter_skills_for_profile, filter_tools_for_profile
from omega_agent.runtime.memory import MemoryStore
from omega_agent.runtime.settings import SettingsStore
from omega_agent.runtime.skills_registry import SkillsRegistry
from omega_agent.runtime.standing_orders import StandingOrdersStore
from omega_agent.runtime.system_prompt import build_system_prompt
from omega_agent.runtime.tools_registry import list_tools


def build_context(
    config: OmegaConfig,
    session_id: str | None,
    query: str = "",
    agent_profile: AgentProfile | None = None,
    *,
    tools: list | None = None,
    skills: list | None = None,
) -> dict:
    profile = agent_profile or AgentProfilesStore(config).profile_for_session(session_id)
    raw_tools = tools if tools is not None else list_tools(config)
    raw_skills = skills if skills is not None else SkillsRegistry(config).list()
    filtered_tools = filter_tools_for_profile(list(raw_tools), profile)[: config.max_tool_descriptions]
    filtered_skills = filter_skills_for_profile([skill for skill in list(raw_skills) if skill.enabled], profile)[: config.max_skills_in_context]
    tools_payload = [_compact_tool(tool) for tool in filtered_tools]
    skills_payload = [_compact_skill(skill) for skill in filtered_skills]
    memories = [asdict(memory) for memory in MemoryStore(config).search(query=query, limit=config.max_memory_results)]
    standing_orders = [asdict(order) for order in StandingOrdersStore(config).active_for_context(session_id=session_id)]
    settings = SettingsStore(config).get_all()
    system_prompt = build_system_prompt(
        config,
        tools=tools_payload,
        skills=skills_payload,
        memories=memories,
        settings=settings,
        agent_profile=profile.as_api(),
        standing_orders=standing_orders,
        policy_notes=[
            "Chemins relatifs au workspace uniquement.",
            "Workspace Full Access actif: actions workspace-safe sans approval systematique." if config.workspace_full_access else "Approvals obligatoires pour write_file et run_shell selon le projet et le profil.",
            f"Tools autorises par profil: {', '.join(profile.allowed_tools) or 'tous'}",
        ],
    )
    return {
        "session_id": session_id,
        "agent_profile": profile.as_api(),
        "tools": tools_payload,
        "skills": skills_payload,
        "memories": memories,
        "standing_orders": standing_orders,
        "settings": settings,
        "system_prompt": system_prompt,
    }


def _compact_tool(tool) -> dict:
    data = asdict(tool)
    return {
        "id": data["id"],
        "name": data["name"],
        "description": str(data["description"])[:220],
        "risk": data.get("risk") or data.get("risk_level") or "medium",
        "risk_level": data.get("risk_level") or data.get("risk") or "medium",
        "enabled": bool(data.get("enabled")),
        "requires_approval": bool(data.get("requires_approval")),
    }


def _compact_skill(skill) -> dict:
    data = asdict(skill)
    return {
        "id": data.get("id") or data.get("name"),
        "name": data["name"],
        "description": str(data.get("description") or "")[:300],
        "risk": data.get("risk") or data.get("risk_level") or "low",
        "risk_level": data.get("risk_level") or data.get("risk") or "low",
        "enabled": bool(data.get("enabled")),
    }
