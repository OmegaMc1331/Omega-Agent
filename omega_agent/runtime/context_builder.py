from __future__ import annotations

from dataclasses import asdict

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfile, AgentProfilesStore, filter_skills_for_profile, filter_tools_for_profile
from omega_agent.runtime.capability_selector import CapabilitySelector
from omega_agent.runtime.project_memory import ProjectMemoryStore
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.repo_analyzer import RepoProfilesStore, summarize_repo
from omega_agent.runtime.settings import SettingsStore
from omega_agent.runtime.skills_registry import SkillsRegistry
from omega_agent.runtime.standing_orders import StandingOrdersStore
from omega_agent.runtime.system_prompt import build_system_prompt
from omega_agent.runtime.test_runner import CodeTestRunner
from omega_agent.runtime.tools_registry import list_tools
from omega_agent.tools.git import git_status


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
    project_id = None
    try:
        project_id = ProjectsStore(config).project_for_session(session_id).id
    except PermissionError:
        project_id = None
    raw_tools = tools if tools is not None else list_tools(config)
    raw_skills = skills if skills is not None else SkillsRegistry(config).list()
    skill_limit = min(config.max_skills_in_context, getattr(config, "skills_max_skills_in_context", config.max_skills_in_context))
    selected_capabilities = []
    if config.capabilities_enabled:
        selected_capabilities = CapabilitySelector(config).select_capabilities_for_task(
            query,
            session_id=session_id,
            project_id=project_id,
            agent_profile_id=profile.id,
        )
        selected_tool_ids = {item.id.split(":", 1)[1] for item in selected_capabilities if item.type == "tool" and ":" in item.id}
        selected_skill_ids = {item.id.split(":", 1)[1] for item in selected_capabilities if item.type == "skill" and ":" in item.id}
        filtered_tools = [tool for tool in filter_tools_for_profile(list(raw_tools), profile) if tool.id in selected_tool_ids][: config.max_tool_descriptions]
        filtered_skills = [
            skill
            for skill in filter_skills_for_profile([skill for skill in list(raw_skills) if skill.enabled], profile)
            if skill.id in selected_skill_ids or skill.name in selected_skill_ids
        ][: skill_limit]
    else:
        filtered_tools = filter_tools_for_profile(list(raw_tools), profile)[: config.max_tool_descriptions]
        filtered_skills = filter_skills_for_profile([skill for skill in list(raw_skills) if skill.enabled], profile)[:skill_limit]
    tools_payload = [_compact_tool(tool) for tool in filtered_tools]
    skills_payload = [_compact_skill(skill) for skill in filtered_skills]
    if getattr(config, "capabilities_usage_logging", True):
        try:
            from omega_agent.skills.skill_usage import SkillUsageStore

            usage = SkillUsageStore(config)
            for skill in filtered_skills[: getattr(config, "skills_max_skills_in_context", config.max_skills_in_context)]:
                if str(getattr(skill, "path", "")).startswith("db://skills/"):
                    usage.record(skill.id, status="selected", metadata={"session_id": session_id, "query": query[:160]})
        except Exception:
            pass
    capabilities_payload = [_compact_capability(capability) for capability in selected_capabilities]
    memory_limit = max(1, min(config.memory_max_context_memories, config.max_memory_results))
    memory_store = ProjectMemoryStore(config)
    memories = [_compact_memory(memory) for memory in memory_store.get_relevant_memories(query, project_id=project_id, session_id=session_id, limit=memory_limit)]
    memory_conflicts = [conflict.as_api() for conflict in memory_store.list_conflicts(project_id=project_id)[:5]]
    code_workspace = _code_workspace_context(config, project_id) if profile.id == "omega-coder" and config.code_enabled else None
    standing_orders = [asdict(order) for order in StandingOrdersStore(config).active_for_context(session_id=session_id)]
    settings = SettingsStore(config).get_all()
    system_prompt = build_system_prompt(
        config,
        tools=tools_payload,
        skills=skills_payload,
        memories=memories,
        settings=settings,
        capabilities=capabilities_payload,
        agent_profile=profile.as_api(),
        standing_orders=standing_orders,
        code_workspace=code_workspace,
        policy_notes=[
            "Chemins relatifs au workspace uniquement.",
            "Workspace Full Access actif: actions workspace-safe sans approval systematique." if config.workspace_full_access else "Approvals obligatoires pour write_file et run_shell selon le projet et le profil.",
            f"Tools autorises par profil: {', '.join(profile.allowed_tools) or 'tous'}",
            f"Capabilities selectionnees pour cette demande: {len(capabilities_payload)} sur maximum {config.capabilities_max_in_context}.",
            "Memoire projet: respecter provenance, confiance et scope; signaler les contradictions ou souvenirs obsoletes.",
        ],
        memory_conflicts=memory_conflicts,
    )
    return {
        "session_id": session_id,
        "agent_profile": profile.as_api(),
        "tools": tools_payload,
        "skills": skills_payload,
        "capabilities": capabilities_payload,
        "memories": memories,
        "memory_conflicts": memory_conflicts,
        "code_workspace": code_workspace,
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


def _compact_capability(capability) -> dict:
    return {
        "id": capability.id,
        "name": capability.name,
        "type": capability.type,
        "description": str(capability.description or "")[:220],
        "risk_level": capability.risk_level,
        "requires_approval": capability.requires_approval_default,
        "auth_status": capability.auth_status,
    }


def _compact_memory(memory) -> dict:
    provenance = memory.provenance if isinstance(memory.provenance, list) else []
    first_source = provenance[0] if provenance else {}
    return {
        "id": memory.id,
        "scope": memory.scope,
        "project_id": memory.project_id,
        "session_id": memory.session_id,
        "run_id": memory.run_id,
        "key": memory.key,
        "content": memory.content,
        "summary": memory.summary,
        "type": memory.type,
        "confidence": memory.confidence,
        "importance": memory.importance,
        "tags": memory.tags,
        "provenance": provenance,
        "source": first_source.get("source_label") or first_source.get("source_type") or "unknown",
        "updated_at": memory.updated_at,
    }


def _code_workspace_context(config: OmegaConfig, project_id: str | None) -> dict:
    repo_store = RepoProfilesStore(config)
    repo = repo_store.get_latest(project_id=project_id)
    if repo is None:
        repo = repo_store.scan(project_id=project_id) if config.code_auto_scan else summarize_repo(config.workspace)
    test_runs = [item.as_api() for item in CodeTestRunner(config).list_runs(project_id=project_id, limit=3)]
    try:
        status = git_status(config)
    except Exception as exc:
        status = str(exc)
    return {
        "repo_summary": {
            "workspace_path": repo.workspace_path,
            "is_git_repo": repo.is_git_repo,
            "languages": repo.languages,
            "frameworks": repo.frameworks,
            "package_managers": repo.package_managers,
            "test_commands": repo.test_commands,
            "build_commands": repo.build_commands,
            "entrypoints": repo.entrypoints,
            "config_files": repo.config_files,
        },
        "recent_test_runs": [
            {
                "id": item["id"],
                "command": item["command"],
                "status": item["status"],
                "summary": item["summary"],
                "completed_at": item.get("completed_at"),
                "classified_error": item.get("metadata", {}).get("classified_error"),
            }
            for item in test_runs
        ],
        "git_status": str(status or "")[:2000],
    }
