from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from omega_agent.codex_backend import CODEX_LOGIN_HINT
from omega_agent.gateway.models import (
    AgentCreateRequest,
    AgentPatchRequest,
    ChannelCreateRequest,
    ChannelPatchRequest,
    ChatRequest,
    ConfigPatchRequest,
    DelegationCreateRequest,
    JobCreateRequest,
    PluginUpdateRequest,
    PluginEnableRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ScheduledTaskCreateRequest,
    ScheduledTaskPatchRequest,
    SessionCreateRequest,
    SessionAgentRequest,
    SessionProjectRequest,
    SessionRenameRequest,
    SettingsPatchRequest,
    SkillCreateRequest,
    SkillUpdateRequest,
    StandingOrderCreateRequest,
    StandingOrderPatchRequest,
    ToolUpdateRequest,
    WebhookMessageRequest,
)
from omega_agent.config import OmegaConfig
from omega_agent.config_store import config_path, expected_secret_status, migrate_env_to_config, parse_cli_value, redact_config_for_display, save_config, set_config_value
from omega_agent.gateway.capability_routes import register_capability_routes
from omega_agent.gateway.budget_routes import register_budget_routes
from omega_agent.gateway.code_routes import register_code_routes
from omega_agent.gateway.connector_routes import register_connector_routes
from omega_agent.gateway.eval_routes import register_eval_routes
from omega_agent.gateway.event_routes import register_event_routes
from omega_agent.gateway.memory_routes import register_memory_routes
from omega_agent.gateway.policy_routes import register_policy_routes
from omega_agent.gateway.research_routes import register_research_routes
from omega_agent.gateway.skill_routes import register_skill_routes
from omega_agent.gateway.shadow_routes import register_shadow_routes
from omega_agent.gateway.workflow_routes import register_workflow_routes
from omega_agent.security.audit import apply_safe_fixes, list_audit_logs, run_security_audit
from omega_agent.security.desktop_policy import desktop_screenshots_dir
from omega_agent.security.redaction import redact
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.settings import SettingsStore
from omega_agent.tools.browser import browser_status, close_browser
from omega_agent.tools.desktop import desktop_status

CODEX_DISCONNECTED_MESSAGE = "Codex n'est pas connecte. Lance : codex login"
VALID_APPROVAL_STATUSES = {"pending", "approved", "rejected", "expired"}


def create_router() -> APIRouter:
    router = APIRouter()
    register_capability_routes(router)
    register_budget_routes(router)
    register_code_routes(router)
    register_connector_routes(router)
    register_eval_routes(router)
    register_event_routes(router)
    register_memory_routes(router)
    register_policy_routes(router)
    register_research_routes(router)
    register_skill_routes(router)
    register_shadow_routes(router)
    register_workflow_routes(router)

    @router.get("/health")
    async def health(request: Request):
        state = request.app.state.gateway_state
        return {"ok": True, "version": state.version, "uptime": _uptime_seconds(state)}

    @router.get("/api/status")
    async def api_status(request: Request):
        state = request.app.state.gateway_state

        def build_payload():
            codex_connected = None
            codex_message = None
            if state.config.provider == "codex":
                codex_connected, codex_message = state.codex_login_status()
            tools = state.tools()
            skills = state.skills_list()
            plugins = state.plugins_list()
            pending_approvals = state.approvals.list(status="pending")
            current_model = state.model_selector.current_api()
            return {
                "ok": True,
                "provider": state.config.provider,
                "model": state.config.model,
                "current_model": current_model,
                "codex_auth_status": "connected" if codex_connected else "disconnected" if codex_connected is False else "not_applicable",
                "workspace": str(state.config.workspace),
                "config_path": str(state.config.config_path or config_path()),
                "config_status": state.config.config_status,
                "legacy_env_present": state.config.legacy_env_present,
                "model_config_source": state.config.model_config_source,
                "version": state.version,
                "uptime": _uptime_seconds(state),
                "host": state.config.host,
                "port": state.config.port,
                "safe_mode": state.config.safe_mode,
                "workspace_full_access": state.config.workspace_full_access,
                "require_approval_outside_workspace": state.config.require_approval_outside_workspace,
                "shell_full_access_in_workspace": state.config.shell_full_access_in_workspace,
                "allow_delete_in_workspace": state.config.allow_delete_in_workspace,
                "allow_git_write_in_workspace": state.config.allow_git_write_in_workspace,
                "reasoning_stream": state.config.reasoning_stream,
                "reasoning_detail": state.config.reasoning_detail,
                "fast_mode": state.config.fast_mode,
                "streaming": state.config.streaming,
                "perf_logging": state.config.perf_logging,
                "tools_count": len(tools),
                "skills_count": len(skills),
                "plugins_count": len(plugins),
                "pending_approvals_count": len(pending_approvals),
                "auth_codex": redact({"connected": codex_connected, "message": codex_message}),
                "gateway": {
                    "name": "Omega Gateway",
                    "ui": "Omega Control",
                    "host": state.config.host,
                    "port": state.config.port,
                    "open_browser": state.config.open_browser,
                    "theme": state.config.ui_theme,
                },
                "codex_connected": codex_connected,
                "codex_message": redact(codex_message),
                "login_hint": None if codex_connected is not False else CODEX_DISCONNECTED_MESSAGE,
            }

        return state.cached_status(build_payload)

    @router.get("/api/performance/recent")
    async def api_performance_recent(request: Request):
        return request.app.state.gateway_state.performance.recent(limit=20)

    @router.get("/api/config")
    async def api_config(request: Request):
        return {"path": str(config_path()), "config": redact_config_for_display()}

    @router.get("/api/config/path")
    async def api_config_path(request: Request):
        return {"path": str(config_path())}

    @router.patch("/api/config")
    async def api_patch_config(payload: ConfigPatchRequest, request: Request):
        allowed_prefixes = (
            "app.",
            "gateway.",
            "mobile.",
            "workspace.",
            "model.",
            "providers.",
            "channels.",
            "scheduler.",
            "reasoning.",
            "runtime.",
            "capabilities.",
            "memory.",
            "code.",
            "self_healing.",
            "evals.",
            "connectors.",
            "events.",
            "research.",
            "shadow.",
            "performance.",
            "paths.",
        )
        try:
            data = None
            for key, value in payload.values.items():
                if not isinstance(key, str) or not key.startswith(allowed_prefixes):
                    raise ValueError(f"Config non modifiable: {key}")
                data = set_config_value(key, parse_cli_value(str(value)) if isinstance(value, str) else value, data)
            if data is not None:
                save_config(data)
            _reload_config_state(request.app.state.gateway_state)
            return {"path": str(config_path()), "config": redact_config_for_display()}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/config/migrate-env")
    async def api_config_migrate_env(request: Request):
        result = migrate_env_to_config()
        _reload_config_state(request.app.state.gateway_state)
        return result

    @router.get("/api/secrets/status")
    async def api_secrets_status(request: Request):
        return expected_secret_status()

    @router.post("/api/registries/reload")
    async def api_reload_registries(request: Request):
        return {"ok": True, **request.app.state.gateway_state.reload_registries()}

    @router.get("/api/security/audit")
    async def api_security_audit(request: Request):
        return run_security_audit(request.app.state.gateway_state.config).as_api()

    @router.post("/api/security/audit/fix-safe")
    async def api_security_audit_fix_safe(request: Request):
        config, fixed = apply_safe_fixes(request.app.state.gateway_state.config)
        request.app.state.gateway_state.config = config
        report = run_security_audit(config)
        return {**report.as_api(), "fixed": fixed}

    @router.get("/api/sessions")
    async def list_sessions(request: Request):
        return [asdict(session) for session in request.app.state.gateway_state.sessions.list_sessions()]

    @router.post("/api/sessions")
    async def create_session(payload: SessionCreateRequest, request: Request):
        state = request.app.state.gateway_state
        session = state.sessions.create_session(payload.title)
        state.events.add("session.created", {"session_id": session.id}, session_id=session.id)
        return asdict(session)

    @router.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, request: Request):
        session = request.app.state.gateway_state.sessions.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return asdict(session)

    @router.patch("/api/sessions/{session_id}")
    async def update_session(session_id: str, payload: SessionRenameRequest, request: Request):
        state = request.app.state.gateway_state
        session = state.sessions.update_session(session_id, title=payload.title, status=payload.status, metadata=payload.metadata)
        if session is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        state.events.add("session.updated", {"session_id": session.id}, session_id=session.id)
        return asdict(session)

    @router.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str, request: Request):
        deleted = request.app.state.gateway_state.sessions.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return {"ok": True}

    @router.post("/api/sessions/{session_id}/project")
    async def set_session_project(session_id: str, payload: SessionProjectRequest, request: Request):
        state = request.app.state.gateway_state
        if state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        project_id = payload.project_id
        if project_id:
            project = state.projects.get(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Projet introuvable ou desactive.")
        session = state.sessions.set_project(session_id, project_id)
        state.events.add("session.project.updated", {"session_id": session_id, "project_id": project_id}, session_id=session_id)
        return asdict(session)

    @router.post("/api/sessions/{session_id}/agent")
    async def set_session_agent(session_id: str, payload: SessionAgentRequest, request: Request):
        state = request.app.state.gateway_state
        current = state.sessions.get_session(session_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        profile = state.agent_profiles.get(payload.agent_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profil agent introuvable ou desactive.")
        session = state.sessions.set_agent_profile(session_id, profile.id)
        state.events.add("agent.switched", {"from": current.active_agent_profile_id, "to": profile.id, "reason": "manual"}, session_id=session_id)
        return asdict(session)

    @router.get("/api/sessions/{session_id}/messages")
    async def list_messages(session_id: str, request: Request):
        if request.app.state.gateway_state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return [asdict(message) for message in request.app.state.gateway_state.sessions.list_messages(session_id)]

    @router.get("/api/sessions/{session_id}/reasoning")
    async def list_session_reasoning(session_id: str, request: Request):
        if request.app.state.gateway_state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return [event.as_api() for event in request.app.state.gateway_state.reasoning.list_for_session(session_id)]

    @router.get("/api/messages/{message_id}/reasoning")
    async def list_message_reasoning(message_id: str, request: Request):
        events = request.app.state.gateway_state.reasoning.list_for_message(message_id)
        return [event.as_api() for event in events]

    @router.get("/api/agents")
    async def list_agents(request: Request):
        return [profile.as_api() for profile in request.app.state.gateway_state.agent_profiles.list()]

    @router.post("/api/agents")
    async def create_agent(payload: AgentCreateRequest, request: Request):
        state = request.app.state.gateway_state
        unknown_tools = sorted(set(payload.allowed_tools) - {tool.id for tool in state.tools()})
        if unknown_tools:
            raise HTTPException(status_code=400, detail=f"Tools inconnus pour le profil: {', '.join(unknown_tools)}")
        try:
            profile = state.agent_profiles.create(
                payload.id,
                payload.name,
                description=payload.description,
                system_prompt=payload.system_prompt,
                enabled=payload.enabled,
                allowed_tools=payload.allowed_tools,
                allowed_skills=payload.allowed_skills,
                risk_level=payload.risk_level,
                policy=payload.policy,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Profil agent deja existant.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.events.add("agent.created", {"agent_id": profile.id})
        return profile.as_api()

    @router.patch("/api/agents/{agent_id}")
    async def update_agent(agent_id: str, payload: AgentPatchRequest, request: Request):
        state = request.app.state.gateway_state
        if payload.allowed_tools is not None:
            unknown_tools = sorted(set(payload.allowed_tools) - {tool.id for tool in state.tools()})
            if unknown_tools:
                raise HTTPException(status_code=400, detail=f"Tools inconnus pour le profil: {', '.join(unknown_tools)}")
        profile = state.agent_profiles.update(
            agent_id,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            enabled=payload.enabled,
            allowed_tools=payload.allowed_tools,
            allowed_skills=payload.allowed_skills,
            risk_level=payload.risk_level,
            policy=payload.policy,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="Profil agent introuvable.")
        state.events.add("agent.updated", {"agent_id": profile.id})
        return profile.as_api()

    @router.delete("/api/agents/{agent_id}")
    async def delete_agent(agent_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            deleted = state.agent_profiles.delete(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Profil agent introuvable.")
        state.events.add("agent.deleted", {"agent_id": agent_id})
        return {"ok": True}

    @router.get("/api/projects")
    async def list_projects(request: Request):
        state = request.app.state.gateway_state
        return [project.as_api(state.projects.linked_session_count(project.id)) for project in state.projects.list()]

    @router.post("/api/projects")
    async def create_project(payload: ProjectCreateRequest, request: Request):
        state = request.app.state.gateway_state
        try:
            project = state.projects.create(
                name=payload.name,
                root_path=payload.root_path,
                description=payload.description,
                enabled=payload.enabled,
                policy=payload.policy,
                metadata=payload.metadata,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.events.add("project.created", {"project_id": project.id})
        return project.as_api(0)

    @router.get("/api/projects/{project_id}")
    async def get_project(project_id: str, request: Request):
        state = request.app.state.gateway_state
        project = state.projects.get(project_id, include_disabled=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Projet introuvable.")
        sessions = [asdict(session) for session in state.sessions.list_sessions() if session.project_id == project.id]
        payload = project.as_api(len(sessions))
        payload["sessions"] = sessions
        payload["permissions"] = [asdict(permission) for permission in state.projects.permissions(project.id)]
        return payload

    @router.patch("/api/projects/{project_id}")
    async def update_project(project_id: str, payload: ProjectPatchRequest, request: Request):
        state = request.app.state.gateway_state
        try:
            project = state.projects.update(
                project_id,
                name=payload.name,
                root_path=payload.root_path,
                description=payload.description,
                enabled=payload.enabled,
                policy=payload.policy,
                metadata=payload.metadata,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if project is None:
            raise HTTPException(status_code=404, detail="Projet introuvable.")
        state.events.add("project.updated", {"project_id": project.id})
        return project.as_api(state.projects.linked_session_count(project.id))

    @router.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            deleted = state.projects.delete(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Projet introuvable.")
        state.events.add("project.deleted", {"project_id": project_id})
        return {"ok": True}

    @router.post("/api/chat")
    async def api_chat(payload: ChatRequest, request: Request):
        message = payload.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message vide.")
        state = request.app.state.gateway_state
        session_id = payload.session_id or state.sessions.default_session_id()
        if state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        try:
            runtime = state.runtime()
            output = await runtime.send_message(
                message,
                session_id=session_id,
                thinking_level=payload.thinking_level,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if output == CODEX_LOGIN_HINT:
            output = CODEX_DISCONNECTED_MESSAGE
        return {"session_id": session_id, "message": output, "run_id": getattr(runtime, "last_run_id", None)}

    @router.get("/api/runs")
    async def api_runs(request: Request, session_id: str | None = None, status: str | None = None, limit: int = Query(50, ge=1, le=500)):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        return [run.as_api() for run in runtime.list_runs(session_id=session_id, status=status, limit=limit)]

    @router.post("/api/runs")
    async def api_create_run(request: Request):
        state = request.app.state.gateway_state
        payload = await request.json()
        session_id = str(payload.get("session_id") or state.sessions.default_session_id())
        if state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        run = DurableRuntime(state.config).create_run(session_id, str(payload.get("message") or payload.get("title") or "Run manuel"), metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {})
        return run.as_api()

    @router.get("/api/runs/{run_id}")
    async def api_get_run(run_id: str, request: Request):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        run = runtime.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run introuvable.")
        return run.as_api()

    @router.get("/api/runs/{run_id}/steps")
    async def api_run_steps(run_id: str, request: Request):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        if runtime.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run introuvable.")
        return [step.as_api() for step in runtime.list_steps(run_id)]

    @router.get("/api/runs/{run_id}/actions")
    async def api_run_actions(run_id: str, request: Request):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        if runtime.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run introuvable.")
        return [action.as_api() for action in runtime.list_actions(run_id)]

    @router.get("/api/runs/{run_id}/checkpoints")
    async def api_run_checkpoints(run_id: str, request: Request):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        if runtime.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run introuvable.")
        return runtime.list_checkpoints(run_id)

    @router.post("/api/runs/{run_id}/pause")
    async def api_pause_run(run_id: str, request: Request):
        return DurableRuntime(request.app.state.gateway_state.config).pause_run(run_id).as_api()

    @router.post("/api/runs/{run_id}/resume")
    async def api_resume_run(run_id: str, request: Request):
        return DurableRuntime(request.app.state.gateway_state.config).resume_run(run_id).as_api()

    @router.post("/api/runs/{run_id}/cancel")
    async def api_cancel_run(run_id: str, request: Request):
        return DurableRuntime(request.app.state.gateway_state.config).cancel_run(run_id).as_api()

    @router.post("/api/runs/{run_id}/replay")
    async def api_replay_run(run_id: str, request: Request):
        payload = await request.json() if request.headers.get("content-length") else {}
        return DurableRuntime(request.app.state.gateway_state.config).replay_run(run_id, dry_run=bool(payload.get("dry_run", True)))

    @router.get("/api/snapshots")
    async def api_snapshots(request: Request, limit: int = Query(100, ge=1, le=500)):
        return [snapshot.as_api() for snapshot in DurableRuntime(request.app.state.gateway_state.config).list_snapshots(limit=limit)]

    @router.get("/api/runs/{run_id}/snapshots")
    async def api_run_snapshots(run_id: str, request: Request):
        runtime = DurableRuntime(request.app.state.gateway_state.config)
        if runtime.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run introuvable.")
        return [snapshot.as_api() for snapshot in runtime.list_snapshots(run_id=run_id)]

    @router.post("/api/snapshots/{snapshot_id}/rollback")
    async def api_rollback_snapshot(snapshot_id: str, request: Request):
        return DurableRuntime(request.app.state.gateway_state.config).rollback_snapshot(snapshot_id)

    @router.post("/api/runs/{run_id}/rollback")
    async def api_rollback_run(run_id: str, request: Request):
        return DurableRuntime(request.app.state.gateway_state.config).rollback_run(run_id)

    @router.get("/api/timeline")
    async def api_timeline(request: Request, limit: int = Query(100, ge=1, le=500)):
        return [asdict(event) for event in request.app.state.gateway_state.events.list_recent(limit=limit)]

    @router.get("/api/sessions/{session_id}/timeline")
    async def api_session_timeline(session_id: str, request: Request, limit: int = Query(100, ge=1, le=500)):
        if request.app.state.gateway_state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return [asdict(event) for event in request.app.state.gateway_state.events.list_recent(limit=limit, session_id=session_id)]

    @router.get("/api/tools")
    async def api_tools(request: Request):
        return [asdict(tool) for tool in request.app.state.gateway_state.tools()]

    @router.get("/api/browser/status")
    async def api_browser_status(request: Request):
        return browser_status(request.app.state.gateway_state.config)

    @router.post("/api/browser/close")
    async def api_browser_close(request: Request):
        close_browser()
        request.app.state.gateway_state.events.add("browser.closed", {})
        return browser_status(request.app.state.gateway_state.config)

    @router.get("/api/browser/screenshot")
    async def api_browser_screenshot_file(request: Request):
        state = request.app.state.gateway_state
        status = browser_status(state.config)
        last_screenshot = str(status.get("last_screenshot") or "")
        if not last_screenshot:
            raise HTTPException(status_code=404, detail="Aucun screenshot navigateur.")
        path = (state.config.workspace / last_screenshot).resolve()
        allowed_root = (state.config.workspace / ".omega" / "browser-screenshots").resolve()
        if os.path.commonpath([str(allowed_root), str(path)]) != str(allowed_root) or not path.exists():
            raise HTTPException(status_code=404, detail="Screenshot navigateur introuvable.")
        return FileResponse(path)

    @router.get("/api/desktop/status")
    async def api_desktop_status(request: Request):
        return desktop_status(request.app.state.gateway_state.config)

    @router.get("/api/desktop/screenshot")
    async def api_desktop_screenshot_file(request: Request):
        state = request.app.state.gateway_state
        status = desktop_status(state.config)
        last_screenshot = str(status.get("last_screenshot") or "")
        if not last_screenshot:
            raise HTTPException(status_code=404, detail="Aucun screenshot desktop.")
        path = (state.config.workspace / last_screenshot).resolve()
        allowed_root = desktop_screenshots_dir(state.config).resolve()
        if os.path.commonpath([str(allowed_root), str(path)]) != str(allowed_root) or not path.exists():
            raise HTTPException(status_code=404, detail="Screenshot desktop introuvable.")
        return FileResponse(path)

    @router.patch("/api/tools/{tool_id}")
    async def api_patch_tool(tool_id: str, payload: ToolUpdateRequest, request: Request):
        tool = next((item for item in request.app.state.gateway_state.tools() if item.id == tool_id), None)
        if tool is None:
            raise HTTPException(status_code=404, detail="Tool introuvable.")
        data = asdict(tool)
        data["enabled"] = payload.enabled
        return data

    @router.get("/api/skills")
    async def api_skills(request: Request):
        return [asdict(skill) for skill in request.app.state.gateway_state.skills_list()]

    @router.post("/api/skills")
    async def api_create_skill(payload: SkillCreateRequest, request: Request):
        if payload.definition is not None:
            from omega_agent.skills.skill_store import SkillStore
            from omega_agent.skills.skill_validator import SkillValidator

            validation = SkillValidator(request.app.state.gateway_state.config).validate(payload.definition, payload.test_cases)
            if not validation.valid:
                raise HTTPException(status_code=400, detail="; ".join(validation.errors))
            skill = SkillStore(request.app.state.gateway_state.config).create_skill(
                name=payload.name,
                description=payload.description,
                skill_type=payload.skill_type or "prompt",
                definition=payload.definition,
                test_cases=payload.test_cases,
                status="draft",
                metadata={**payload.metadata, "trust_level": "untrusted", "imported": True},
            )
            request.app.state.gateway_state.reload_registries(log_event=False)
            request.app.state.gateway_state.events.add("skill.created", {"skill_id": skill.id, "status": "draft", "imported": True})
            return skill.as_api()
        allowed_tool_ids = {tool.id for tool in request.app.state.gateway_state.tools()}
        unknown_tools = sorted(set(payload.tools) - allowed_tool_ids)
        if unknown_tools:
            raise HTTPException(status_code=400, detail=f"Tools inconnus pour la skill: {', '.join(unknown_tools)}")
        try:
            skill = request.app.state.gateway_state.skills.create(
                name=payload.name,
                description=payload.description,
                instructions=payload.instructions,
                tools=payload.tools,
                risk=payload.risk,
                tags=payload.tags,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Skill deja existante.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.gateway_state.reload_registries(log_event=False)
        return asdict(skill)

    @router.patch("/api/skills/{skill_id}")
    async def api_update_skill(skill_id: str, payload: SkillUpdateRequest, request: Request):
        from omega_agent.skills.skill_promoter import SkillPromoter
        from omega_agent.skills.skill_store import SkillStore
        from omega_agent.skills.skill_validator import SkillValidator

        state = request.app.state.gateway_state
        store = SkillStore(state.config)
        foundry = store.get_skill(skill_id)
        if foundry is not None:
            patch = payload.model_dump(exclude_none=True, exclude={"enabled", "changelog"})
            if patch:
                definition = patch.get("definition", foundry.definition)
                tests = patch.get("test_cases", foundry.test_cases)
                validation = SkillValidator(state.config).validate(definition, tests)
                if not validation.valid:
                    raise HTTPException(status_code=400, detail="; ".join(validation.errors))
                foundry = store.update_skill(skill_id, patch, changelog=payload.changelog)
            if payload.enabled is not None:
                try:
                    foundry = SkillPromoter(state.config).activate(skill_id) if payload.enabled else SkillPromoter(state.config).disable(skill_id)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            state.reload_registries(log_event=False)
            return foundry.as_api()
        if payload.enabled is None:
            raise HTTPException(status_code=400, detail="Le champ enabled est requis pour une skill legacy.")
        try:
            skill = request.app.state.gateway_state.skills.set_enabled(skill_id, payload.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill introuvable.")
        request.app.state.gateway_state.reload_registries(log_event=False)
        return asdict(skill)

    @router.delete("/api/skills/{skill_id}")
    async def api_delete_skill(skill_id: str, request: Request):
        try:
            deleted = request.app.state.gateway_state.skills.delete(skill_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Skill introuvable.")
        request.app.state.gateway_state.reload_registries(log_event=False)
        return {"ok": True}

    @router.get("/api/plugins")
    async def api_plugins(request: Request):
        return [asdict(plugin) for plugin in request.app.state.gateway_state.plugins_list()]

    @router.post("/api/plugins/rescan")
    async def api_rescan_plugins(request: Request):
        state = request.app.state.gateway_state
        plugins = state.plugins.rescan()
        state.reload_registries(log_event=False)
        state.events.add("plugins.rescanned", {"count": len(plugins)})
        return [asdict(plugin) for plugin in plugins]

    @router.get("/api/plugins/{plugin_id}")
    async def api_get_plugin(plugin_id: str, request: Request):
        plugin = request.app.state.gateway_state.plugins.get(plugin_id)
        if plugin is None:
            raise HTTPException(status_code=404, detail="Plugin introuvable.")
        return asdict(plugin)

    @router.get("/api/plugins/{plugin_id}/security-review")
    async def api_plugin_security_review(plugin_id: str, request: Request):
        review = request.app.state.gateway_state.plugins.security_review(plugin_id)
        if review is None:
            raise HTTPException(status_code=404, detail="Plugin introuvable.")
        return review

    @router.post("/api/plugins/{plugin_id}/enable")
    async def api_enable_plugin(plugin_id: str, payload: PluginEnableRequest, request: Request):
        try:
            plugin = request.app.state.gateway_state.plugins.set_enabled(plugin_id, True, confirmed=payload.confirmed)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if plugin is None:
            raise HTTPException(status_code=404, detail="Plugin introuvable.")
        request.app.state.gateway_state.reload_registries(log_event=False)
        request.app.state.gateway_state.events.add("plugin.enabled", {"plugin_id": plugin.id})
        return asdict(plugin)

    @router.post("/api/plugins/{plugin_id}/disable")
    async def api_disable_plugin(plugin_id: str, request: Request):
        try:
            plugin = request.app.state.gateway_state.plugins.set_enabled(plugin_id, False)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if plugin is None:
            raise HTTPException(status_code=404, detail="Plugin introuvable.")
        request.app.state.gateway_state.reload_registries(log_event=False)
        request.app.state.gateway_state.events.add("plugin.disabled", {"plugin_id": plugin.id})
        return asdict(plugin)

    @router.patch("/api/plugins/{plugin_id}")
    async def api_patch_plugin(plugin_id: str, payload: PluginUpdateRequest, request: Request):
        try:
            plugin = request.app.state.gateway_state.plugins.set_enabled(plugin_id, payload.enabled, confirmed=payload.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if plugin is None:
            raise HTTPException(status_code=404, detail="Plugin introuvable.")
        request.app.state.gateway_state.reload_registries(log_event=False)
        return asdict(plugin)

    @router.get("/api/channels")
    async def api_channels(request: Request):
        return [channel.as_api() for channel in request.app.state.gateway_state.channels.list()]

    @router.post("/api/channels")
    async def api_create_channel(payload: ChannelCreateRequest, request: Request):
        state = request.app.state.gateway_state
        try:
            channel = state.channels.create(payload.id, payload.type, payload.name, enabled=payload.enabled, config=payload.config)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail="Channel deja existant.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        state.events.add("channel.created", {"channel_id": channel.id, "type": channel.type})
        return channel.as_api()

    @router.patch("/api/channels/{channel_id}")
    async def api_update_channel(channel_id: str, payload: ChannelPatchRequest, request: Request):
        state = request.app.state.gateway_state
        channel = state.channels.update(channel_id, name=payload.name, enabled=payload.enabled, config=payload.config)
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel introuvable.")
        state.events.add("channel.updated", {"channel_id": channel.id, "type": channel.type})
        return channel.as_api()

    @router.delete("/api/channels/{channel_id}")
    async def api_delete_channel(channel_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            deleted = state.channels.delete(channel_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Channel introuvable.")
        state.events.add("channel.updated", {"channel_id": channel_id, "deleted": True})
        return {"ok": True}

    @router.post("/api/channels/{channel_id}/test")
    async def api_test_channel(channel_id: str, request: Request):
        state = request.app.state.gateway_state
        try:
            result = state.channels.test(channel_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        event_type = "channel.error" if not result["ok"] else "channel.updated"
        state.events.add(event_type, {"channel_id": channel_id, "status": result["status"], "message": result["message"]})
        return redact(result)

    @router.post("/api/webhooks/{webhook_id}")
    async def api_receive_webhook(webhook_id: str, payload: WebhookMessageRequest, request: Request):
        state = request.app.state.gateway_state
        channel = state.channels.get(webhook_id)
        if channel is None or channel.type != "webhook":
            raise HTTPException(status_code=404, detail="Webhook introuvable.")
        if not channel.enabled:
            raise HTTPException(status_code=403, detail="Webhook desactive.")
        route_to_agent = payload.route_to_agent or str(channel.config.get("route_to_agent") or "")
        if route_to_agent:
            profile = state.agent_profiles.get(route_to_agent)
            if profile is None:
                raise HTTPException(status_code=400, detail="Profil agent route introuvable ou desactive.")
        session_id, account = state.channels.session_for_incoming(
            channel,
            payload.external_account_id,
            display_name=payload.display_name,
            route_to_agent=route_to_agent,
        )
        state.sessions.merge_metadata(
            session_id,
            {
                "channel_id": channel.id,
                "channel_type": channel.type,
                "external_channel": True,
                "untrusted_input": True,
                "channel_account_id": account.id,
            },
        )
        state.events.add(
            "channel.message.received",
            {"channel_id": channel.id, "channel_type": channel.type, "account_id": account.id, "untrusted_input": True, "metadata": redact(payload.metadata)},
            session_id=session_id,
        )
        try:
            output = await state.runtime().send_message(
                payload.message,
                session_id=session_id,
                channel_id=channel.id,
                channel_type=channel.type,
                untrusted_input=True,
            )
        except PermissionError as exc:
            state.events.add("channel.error", {"channel_id": channel.id, "reason": str(exc)}, session_id=session_id)
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if output == CODEX_LOGIN_HINT:
            output = CODEX_DISCONNECTED_MESSAGE
        state.events.add("channel.message.sent", {"channel_id": channel.id, "channel_type": channel.type}, session_id=session_id)
        return {"ok": True, "session_id": session_id, "message": output}

    @router.get("/api/approvals")
    async def api_approvals(request: Request, status: str | None = None):
        if status is not None and status not in VALID_APPROVAL_STATUSES:
            raise HTTPException(status_code=400, detail="Status approval invalide.")
        return [_redact_record(asdict(approval)) for approval in request.app.state.gateway_state.approvals.list(status=status)]

    @router.post("/api/approvals/{approval_id}/approve")
    async def approve(approval_id: str, request: Request):
        approval = request.app.state.gateway_state.approvals.resolve(approval_id, approved=True)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval introuvable.")
        return _redact_record(asdict(approval))

    @router.post("/api/approvals/{approval_id}/reject")
    async def reject(approval_id: str, request: Request):
        approval = request.app.state.gateway_state.approvals.resolve(approval_id, approved=False)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval introuvable.")
        return _redact_record(asdict(approval))

    @router.get("/api/scheduled-tasks")
    async def api_scheduled_tasks(request: Request):
        return [asdict(task) for task in request.app.state.gateway_state.scheduled_tasks.list()]

    @router.post("/api/scheduled-tasks")
    async def api_create_scheduled_task(payload: ScheduledTaskCreateRequest, request: Request):
        try:
            task = request.app.state.gateway_state.scheduled_tasks.create(
                payload.title,
                payload.prompt,
                schedule_type=payload.schedule_type,
                schedule_value=payload.schedule_value,
                enabled=payload.enabled,
                metadata=payload.metadata,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.gateway_state.events.add("scheduled_task.created", {"task_id": task.id})
        return asdict(task)

    @router.patch("/api/scheduled-tasks/{task_id}")
    async def api_update_scheduled_task(task_id: str, payload: ScheduledTaskPatchRequest, request: Request):
        try:
            task = request.app.state.gateway_state.scheduled_tasks.update(
                task_id,
                title=payload.title,
                prompt=payload.prompt,
                schedule_type=payload.schedule_type,
                schedule_value=payload.schedule_value,
                enabled=payload.enabled,
                metadata=payload.metadata,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="Tache planifiee introuvable.")
        request.app.state.gateway_state.events.add("scheduled_task.updated", {"task_id": task.id})
        return asdict(task)

    @router.delete("/api/scheduled-tasks/{task_id}")
    async def api_delete_scheduled_task(task_id: str, request: Request):
        deleted = request.app.state.gateway_state.scheduled_tasks.delete(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Tache planifiee introuvable.")
        request.app.state.gateway_state.events.add("scheduled_task.deleted", {"task_id": task_id})
        return {"ok": True}

    @router.post("/api/scheduled-tasks/{task_id}/run-now")
    async def api_run_scheduled_task_now(task_id: str, request: Request):
        try:
            task, job = request.app.state.gateway_state.scheduled_tasks.run_now(task_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        request.app.state.gateway_state.events.add("scheduled_task.run_now", {"task_id": task.id, "job_id": job.id})
        return {"task": asdict(task), "job": asdict(job)}

    @router.get("/api/standing-orders")
    async def api_standing_orders(request: Request, scope: str | None = None):
        try:
            return [asdict(order) for order in request.app.state.gateway_state.standing_orders.list(scope=scope)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/standing-orders")
    async def api_create_standing_order(payload: StandingOrderCreateRequest, request: Request):
        try:
            order = request.app.state.gateway_state.standing_orders.create(
                payload.title,
                payload.content,
                scope=payload.scope,
                enabled=payload.enabled,
                priority=payload.priority,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.gateway_state.events.add("standing_order.created", {"order_id": order.id})
        return asdict(order)

    @router.patch("/api/standing-orders/{order_id}")
    async def api_update_standing_order(order_id: str, payload: StandingOrderPatchRequest, request: Request):
        try:
            order = request.app.state.gateway_state.standing_orders.update(
                order_id,
                title=payload.title,
                content=payload.content,
                scope=payload.scope,
                enabled=payload.enabled,
                priority=payload.priority,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if order is None:
            raise HTTPException(status_code=404, detail="Standing order introuvable.")
        request.app.state.gateway_state.events.add("standing_order.updated", {"order_id": order.id})
        return asdict(order)

    @router.delete("/api/standing-orders/{order_id}")
    async def api_delete_standing_order(order_id: str, request: Request):
        deleted = request.app.state.gateway_state.standing_orders.delete(order_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Standing order introuvable.")
        request.app.state.gateway_state.events.add("standing_order.deleted", {"order_id": order_id})
        return {"ok": True}

    @router.get("/api/delegations")
    async def api_delegations(request: Request, session_id: str | None = None):
        return [asdict(delegation) for delegation in request.app.state.gateway_state.delegations.list(session_id=session_id)]

    @router.post("/api/delegations")
    async def api_create_delegation(payload: DelegationCreateRequest, request: Request):
        state = request.app.state.gateway_state
        if state.sessions.get_session(payload.session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        try:
            delegation = state.multi_agent.delegate(
                payload.session_id,
                payload.child_agent_id,
                payload.task,
                parent_agent_id=payload.parent_agent_id,
                max_steps=payload.max_steps,
                allowed_tools=payload.allowed_tools,
                run_now=payload.run_now,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return asdict(delegation)

    @router.get("/api/delegations/{delegation_id}")
    async def api_get_delegation(delegation_id: str, request: Request):
        delegation = request.app.state.gateway_state.delegations.get(delegation_id)
        if delegation is None:
            raise HTTPException(status_code=404, detail="Delegation introuvable.")
        return asdict(delegation)

    @router.post("/api/delegations/{delegation_id}/cancel")
    async def api_cancel_delegation(delegation_id: str, request: Request):
        delegation = request.app.state.gateway_state.delegations.cancel(delegation_id)
        if delegation is None:
            raise HTTPException(status_code=404, detail="Delegation introuvable.")
        request.app.state.gateway_state.events.add("delegation.failed", {"delegation_id": delegation.id, "status": "cancelled"}, session_id=delegation.session_id)
        return asdict(delegation)

    @router.get("/api/jobs")
    async def api_jobs(request: Request):
        return [asdict(job) for job in request.app.state.gateway_state.jobs.list()]

    @router.post("/api/jobs")
    async def api_create_job(payload: JobCreateRequest, request: Request):
        if payload.kind == "summarize_session":
            session_id = str(payload.input.get("session_id") or "")
            if not session_id or request.app.state.gateway_state.sessions.get_session(session_id) is None:
                raise HTTPException(status_code=400, detail="summarize_session exige une session valide.")
        if payload.kind == "run_scheduled_prompt" and not str(payload.input.get("prompt") or "").strip():
            raise HTTPException(status_code=400, detail="run_scheduled_prompt exige un prompt.")
        try:
            job = request.app.state.gateway_state.jobs.create(payload.title or payload.kind, payload.kind, payload.input)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return asdict(job)

    @router.post("/api/jobs/{job_id}/cancel")
    async def api_cancel_job(job_id: str, request: Request):
        job = request.app.state.gateway_state.jobs.cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job introuvable.")
        return asdict(job)

    @router.get("/api/events")
    async def api_events(request: Request, limit: int = Query(100, ge=1, le=500), type: str | None = None, session_id: str | None = None):
        if session_id is not None and request.app.state.gateway_state.sessions.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="Session introuvable.")
        return [asdict(event) for event in request.app.state.gateway_state.events.list_recent(limit=limit, event_type=type, session_id=session_id)]

    @router.get("/api/logs")
    async def api_logs(request: Request, limit: int = 100):
        log_file = request.app.state.gateway_state.config.workspace / ".omega" / "actions.jsonl"
        logs = []
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
            for line in lines:
                try:
                    logs.append(redact(json.loads(line)))
                except json.JSONDecodeError:
                    logs.append({"raw": redact(line)})
        logs.extend(redact(list_audit_logs(request.app.state.gateway_state.config, limit=limit)))
        return list(reversed(logs))[-limit:]

    @router.get("/api/settings")
    async def api_settings(request: Request):
        return request.app.state.gateway_state.settings.get_all()

    @router.patch("/api/settings")
    async def api_patch_settings(payload: SettingsPatchRequest, request: Request):
        try:
            state = request.app.state.gateway_state
            result = state.settings.patch(payload.values)
            _persist_settings_to_config(payload.values)
            state.config = _patched_runtime_config(state.config, payload.values)
            state.settings = SettingsStore(state.config)
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


def _uptime_seconds(state) -> int:
    return int((datetime.now(timezone.utc) - state.started_at).total_seconds())


def _reload_config_state(state) -> None:
    state.config = OmegaConfig.from_env()
    state.settings = SettingsStore(state.config)
    state.model_selector = type(state.model_selector)(state.config)
    state._runtime = None
    state.reload_registries(log_event=False)


def _redact_record(record: dict) -> dict:
    redacted = redact(record)
    if "arguments_json" in redacted:
        try:
            redacted["arguments_json"] = json.dumps(redact(json.loads(redacted["arguments_json"])), ensure_ascii=False)
        except (TypeError, json.JSONDecodeError):
            redacted["arguments_json"] = redact(str(redacted["arguments_json"]))
    return redacted


def _patched_runtime_config(config, values: dict):
    mapping = {
        "open_browser": "open_browser",
        "safe_mode": "safe_mode",
        "require_approvals": "require_approval",
        "workspace_full_access": "workspace_full_access",
        "require_approval_outside_workspace": "require_approval_outside_workspace",
        "shell_full_access_in_workspace": "shell_full_access_in_workspace",
        "allow_delete_in_workspace": "allow_delete_in_workspace",
        "allow_git_write_in_workspace": "allow_git_write_in_workspace",
        "runtime_checkpoints_enabled": "runtime_checkpoints_enabled",
        "runtime_snapshots_enabled": "runtime_snapshots_enabled",
        "runtime_snapshots_max_file_size_mb": "runtime_snapshots_max_file_size_mb",
        "runtime_snapshots_keep_days": "runtime_snapshots_keep_days",
        "runtime_replay_enabled": "runtime_replay_enabled",
        "runtime_resume_interrupted_runs": "runtime_resume_interrupted_runs",
        "runtime_max_tool_iterations": "runtime_max_tool_iterations",
        "runtime_max_actions_per_turn": "runtime_max_actions_per_turn",
        "runtime_max_run_seconds": "runtime_max_run_seconds",
        "runtime_dead_letter_enabled": "runtime_dead_letter_enabled",
        "capabilities_enabled": "capabilities_enabled",
        "capabilities_max_in_context": "capabilities_max_in_context",
        "capabilities_mcp_enabled": "capabilities_mcp_enabled",
        "capabilities_a2a_enabled": "capabilities_a2a_enabled",
        "capabilities_untrusted_disabled_by_default": "capabilities_untrusted_disabled_by_default",
        "capabilities_usage_logging": "capabilities_usage_logging",
        "memory_enabled": "memory_enabled",
        "memory_project_memory_enabled": "memory_project_memory_enabled",
        "memory_auto_capture_decisions": "memory_auto_capture_decisions",
        "memory_auto_capture_tool_lessons": "memory_auto_capture_tool_lessons",
        "memory_max_context_memories": "memory_max_context_memories",
        "memory_default_ttl_days": "memory_default_ttl_days",
        "memory_redaction_enabled": "memory_redaction_enabled",
        "memory_require_provenance": "memory_require_provenance",
        "memory_compaction_enabled": "memory_compaction_enabled",
        "code_enabled": "code_enabled",
        "code_auto_scan": "code_auto_scan",
        "code_test_timeout_seconds": "code_test_timeout_seconds",
        "code_max_output_chars": "code_max_output_chars",
        "code_allow_npm_install": "code_allow_npm_install",
        "code_allow_pip_install": "code_allow_pip_install",
        "code_allow_git_commit": "code_allow_git_commit",
        "code_allow_git_push": "code_allow_git_push",
            "self_healing_enabled": "self_healing_enabled",
            "self_healing_max_attempts": "self_healing_max_attempts",
            "self_healing_auto_apply_safe_recoveries": "self_healing_auto_apply_safe_recoveries",
            "evals_enabled": "evals_enabled",
            "evals_auto_score_runs": "evals_auto_score_runs",
            "evals_collect_metrics": "evals_collect_metrics",
            "evals_redact_traces": "evals_redact_traces",
            "evals_max_trace_chars": "evals_max_trace_chars",
            "evals_failure_clustering_enabled": "evals_failure_clustering_enabled",
            "evals_default_dataset_dir": "evals_default_dataset_dir",
            "evals_report_dir": "evals_report_dir",
            "events_enabled": "events_enabled",
            "events_persist": "events_persist",
            "events_replay_enabled": "events_replay_enabled",
            "events_max_replay_events": "events_max_replay_events",
            "events_redaction_enabled": "events_redaction_enabled",
            "events_websocket_heartbeat_seconds": "events_websocket_heartbeat_seconds",
            "research_enabled": "research_enabled",
            "research_max_sources": "research_max_sources",
            "research_max_claims": "research_max_claims",
            "research_require_evidence_for_claims": "research_require_evidence_for_claims",
            "research_export_dir": "research_export_dir",
            "research_web_enabled": "research_web_enabled",
            "research_external_sources_untrusted": "research_external_sources_untrusted",
            "skills_enabled": "skills_enabled",
            "skills_foundry_enabled": "skills_foundry_enabled",
            "skills_auto_detect_candidates": "skills_auto_detect_candidates",
            "skills_min_successful_runs_for_candidate": "skills_min_successful_runs_for_candidate",
            "skills_require_user_approval_for_promotion": "skills_require_user_approval_for_promotion",
            "skills_max_skills_in_context": "skills_max_skills_in_context",
            "skills_test_before_activation": "skills_test_before_activation",
            "governance_budgets_enabled": "governance_budgets_enabled",
            "governance_budgets_default_profile": "governance_budgets_default_profile",
            "governance_budgets_enforce": "governance_budgets_enforce",
            "governance_budgets_warning_threshold": "governance_budgets_warning_threshold",
            "governance_risk_governor_enabled": "governance_risk_governor_enabled",
            "governance_risk_governor_default_max_risk": "governance_risk_governor_default_max_risk",
            "shadow_enabled": "shadow_enabled",
            "shadow_require_for_high_risk": "shadow_require_for_high_risk",
            "shadow_require_for_workflows_over_steps": "shadow_require_for_workflows_over_steps",
            "shadow_workspace_keep_days": "shadow_workspace_keep_days",
            "shadow_max_shadow_seconds": "shadow_max_shadow_seconds",
            "shadow_allow_shell_in_shadow": "shadow_allow_shell_in_shadow",
            "shadow_auto_promote_low_risk": "shadow_auto_promote_low_risk",
            "shadow_compare_after_live": "shadow_compare_after_live",
        }
    updates = {}
    for key, attr in mapping.items():
        if key not in values:
            continue
        value = values[key]
        if attr.startswith("runtime_max") or attr in {
            "runtime_snapshots_max_file_size_mb",
            "runtime_snapshots_keep_days",
            "capabilities_max_in_context",
            "memory_max_context_memories",
            "code_test_timeout_seconds",
            "code_max_output_chars",
            "self_healing_max_attempts",
            "evals_max_trace_chars",
            "events_max_replay_events",
            "events_websocket_heartbeat_seconds",
            "research_max_sources",
            "research_max_claims",
            "skills_min_successful_runs_for_candidate",
            "skills_max_skills_in_context",
            "shadow_require_for_workflows_over_steps",
            "shadow_workspace_keep_days",
            "shadow_max_shadow_seconds",
        }:
            updates[attr] = int(value)
        elif attr == "memory_default_ttl_days":
            updates[attr] = None if value in {None, "", "none", "null"} else int(value)
        elif attr in {"evals_default_dataset_dir", "evals_report_dir"}:
            updates[attr] = Path(str(value)).expanduser().resolve()
        elif attr == "research_export_dir":
            updates[attr] = str(value)
        elif attr in {"governance_budgets_default_profile", "governance_risk_governor_default_max_risk"}:
            updates[attr] = str(value)
        elif attr == "governance_budgets_warning_threshold":
            updates[attr] = max(0.1, min(1.0, float(value)))
        else:
            updates[attr] = bool(value)
    return replace(config, **updates) if updates else config


def _persist_settings_to_config(values: dict) -> None:
    mapping = {
        "open_browser": "app.open_browser",
        "workspace_full_access": "workspace.full_access",
        "require_approvals": "workspace.require_approval",
        "require_approval_outside_workspace": "workspace.require_approval_outside_workspace",
        "shell_full_access_in_workspace": "workspace.shell_full_access",
        "allow_delete_in_workspace": "workspace.allow_delete",
        "allow_git_write_in_workspace": "workspace.allow_git_write",
        "theme": "app.ui_theme",
        "default_model_ref": "model.default",
        "fallback_model_ref": "model.fallback",
        "model_selection_enabled": "model.selection_enabled",
        "runtime_checkpoints_enabled": "runtime.checkpoints.enabled",
        "runtime_snapshots_enabled": "runtime.snapshots.enabled",
        "runtime_snapshots_max_file_size_mb": "runtime.snapshots.max_file_size_mb",
        "runtime_snapshots_keep_days": "runtime.snapshots.keep_days",
        "runtime_replay_enabled": "runtime.replay.enabled",
        "runtime_resume_interrupted_runs": "runtime.resume_interrupted_runs",
        "runtime_max_tool_iterations": "runtime.max_tool_iterations",
        "runtime_max_actions_per_turn": "runtime.max_actions_per_turn",
        "runtime_max_run_seconds": "runtime.max_run_seconds",
        "runtime_dead_letter_enabled": "runtime.dead_letter_enabled",
        "capabilities_enabled": "capabilities.enabled",
        "capabilities_max_in_context": "capabilities.max_in_context",
        "capabilities_mcp_enabled": "capabilities.mcp_enabled",
        "capabilities_a2a_enabled": "capabilities.a2a_enabled",
        "capabilities_untrusted_disabled_by_default": "capabilities.untrusted_disabled_by_default",
        "capabilities_usage_logging": "capabilities.usage_logging",
        "memory_enabled": "memory.enabled",
        "memory_project_memory_enabled": "memory.project_memory_enabled",
        "memory_auto_capture_decisions": "memory.auto_capture_decisions",
        "memory_auto_capture_tool_lessons": "memory.auto_capture_tool_lessons",
        "memory_max_context_memories": "memory.max_context_memories",
        "memory_default_ttl_days": "memory.default_ttl_days",
        "memory_redaction_enabled": "memory.redaction_enabled",
        "memory_require_provenance": "memory.require_provenance",
        "memory_compaction_enabled": "memory.compaction_enabled",
        "code_enabled": "code.enabled",
        "code_auto_scan": "code.auto_scan",
        "code_test_timeout_seconds": "code.test_timeout_seconds",
        "code_max_output_chars": "code.max_output_chars",
        "code_allow_npm_install": "code.allow_npm_install",
        "code_allow_pip_install": "code.allow_pip_install",
        "code_allow_git_commit": "code.allow_git_commit",
        "code_allow_git_push": "code.allow_git_push",
        "self_healing_enabled": "self_healing.enabled",
        "self_healing_max_attempts": "self_healing.max_attempts",
        "self_healing_auto_apply_safe_recoveries": "self_healing.auto_apply_safe_recoveries",
        "evals_enabled": "evals.enabled",
        "evals_auto_score_runs": "evals.auto_score_runs",
        "evals_collect_metrics": "evals.collect_metrics",
        "evals_redact_traces": "evals.redact_traces",
        "evals_max_trace_chars": "evals.max_trace_chars",
        "evals_failure_clustering_enabled": "evals.failure_clustering_enabled",
        "evals_default_dataset_dir": "evals.default_dataset_dir",
        "evals_report_dir": "evals.report_dir",
        "research_enabled": "research.enabled",
        "research_max_sources": "research.max_sources",
        "research_max_claims": "research.max_claims",
        "research_require_evidence_for_claims": "research.require_evidence_for_claims",
        "research_export_dir": "research.export_dir",
        "research_web_enabled": "research.web_enabled",
        "research_external_sources_untrusted": "research.external_sources_untrusted",
        "skills_enabled": "skills.enabled",
        "skills_foundry_enabled": "skills.foundry_enabled",
        "skills_auto_detect_candidates": "skills.auto_detect_candidates",
        "skills_min_successful_runs_for_candidate": "skills.min_successful_runs_for_candidate",
        "skills_require_user_approval_for_promotion": "skills.require_user_approval_for_promotion",
        "skills_max_skills_in_context": "skills.max_skills_in_context",
        "skills_test_before_activation": "skills.test_before_activation",
        "governance_budgets_enabled": "governance.budgets.enabled",
        "governance_budgets_default_profile": "governance.budgets.default_profile",
        "governance_budgets_enforce": "governance.budgets.enforce",
        "governance_budgets_warning_threshold": "governance.budgets.warning_threshold",
        "governance_risk_governor_enabled": "governance.risk_governor.enabled",
        "governance_risk_governor_default_max_risk": "governance.risk_governor.default_max_risk",
        "shadow_enabled": "shadow.enabled",
        "shadow_require_for_high_risk": "shadow.require_for_high_risk",
        "shadow_require_for_workflows_over_steps": "shadow.require_for_workflows_over_steps",
        "shadow_workspace_keep_days": "shadow.workspace_keep_days",
        "shadow_max_shadow_seconds": "shadow.max_shadow_seconds",
        "shadow_allow_shell_in_shadow": "shadow.allow_shell_in_shadow",
        "shadow_auto_promote_low_risk": "shadow.auto_promote_low_risk",
        "shadow_compare_after_live": "shadow.compare_after_live",
    }
    data = None
    for key, config_key in mapping.items():
        if key in values:
            data = set_config_value(config_key, values[key], data)
    if data is not None:
        save_config(data)
