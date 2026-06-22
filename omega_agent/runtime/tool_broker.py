from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.connectors.connector_policy import build_connector_policy_context
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.action_journal import snapshot_paths_for_tool, tool_modifies_files
from omega_agent.runtime.capability_usage import CapabilityUsageStore
from omega_agent.runtime.checkpoints import checkpoint_state
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.multi_agent import MultiAgentRuntime
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.reasoning import emit_reasoning_event
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tools_registry import HANDLERS, ToolsRegistry
from omega_agent.security import log_action, workspace_policy_decision
from omega_agent.security.browser_policy import browser_action_requires_approval, validate_browser_tool_request
from omega_agent.security.desktop_policy import desktop_action_requires_approval, validate_desktop_tool_request
from omega_agent.security.policy_rules import classify_action as classify_policy_action
from omega_agent.security.policy_rules import is_workspace_resource
from omega_agent.security.project_policy import project_config, validate_project_tool
from omega_agent.security.risk import classify_action_risk, max_risk_level
from omega_agent.tools.desktop import active_window_title


@dataclass(frozen=True)
class ToolResult:
    status: str
    output: str
    approval_id: str | None = None
    metadata: dict = field(default_factory=dict)


_WORKSPACE_FULL_ACCESS_TOOLS = {
    "write_file",
    "append_file",
    "delete_file",
    "create_directory",
    "delete_directory",
    "move_file",
    "copy_file",
    "list_tree",
    "file_exists",
    "run_shell",
    "git_add",
    "git_commit",
    "git_restore_file",
}


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
        self.durable = DurableRuntime(config)
        self.capability_usage = CapabilityUsageStore(config)
        self.budgets = BudgetEnforcer(config)

    def call(
        self,
        tool_id: str,
        arguments: dict,
        session_id: str | None = None,
        approval_id: str | None = None,
        run_id: str | None = None,
        *,
        execution_mode: str = "live",
        shadow_workspace: Path | str | None = None,
        shadow_run_id: str | None = None,
    ) -> ToolResult:
        arguments = _normalize_tool_arguments(tool_id, dict(arguments or {}))
        if execution_mode == "shadow":
            return self._call_shadow(
                tool_id,
                arguments,
                session_id=session_id,
                shadow_workspace=shadow_workspace,
                shadow_run_id=shadow_run_id,
            )
        if execution_mode != "live":
            return ToolResult("denied", "Mode d'exécution inconnu.")
        session_id, run_id, owns_run = self._ensure_run_context(session_id, run_id, tool_id)
        step = self.durable.append_step(run_id, "tool_call", tool_id, input={"tool_name": tool_id, "arguments": arguments}, status="running")
        tool = self.registry.get(tool_id)
        if tool is None or not tool.enabled:
            delete_disabled = tool_id in {"delete_file", "delete_directory"} and not self.config.allow_delete_in_workspace
            reason = "Suppression refusee: workspace.allow_delete=false." if delete_disabled else "Tool introuvable ou desactive."
            decision = {
                "action": "deny",
                "reason": reason,
                "risk_level": "high" if delete_disabled else "critical",
                "action_category": "destructive_write" if delete_disabled else "system_sensitive",
            }
            action = self.durable.record_action(run_id, tool_id, arguments, decision, step_id=step.id)
            self.durable.fail_step(step.id, reason)
            if owns_run:
                self.durable.fail_run(run_id, reason)
            self._record_capability_usage(tool_id, "denied", run_id, session_id, error=reason)
            return ToolResult("denied", reason)
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
            workspace_full_access_tool = self.config.workspace_full_access and tool_id in _WORKSPACE_FULL_ACCESS_TOOLS
            if profile.allowed_tools and tool_id not in profile.allowed_tools and not workspace_full_access_tool:
                raise PermissionError(f"Tool non autorise par le profil agent: {tool_id}")
            project = self.projects.project_for_session(session_id)
            project_policy = project.policy
            if self.config.workspace_full_access and not _path_inside_workspace(self.config.workspace, Path(project.root_path)):
                raise PermissionError("Projet hors OMEGA_WORKSPACE refuse en Workspace Full Access.")
            validate_project_tool(tool_id, arguments, project.root_path, project_policy, self.config)
            active_config = project_config(self.config, project.root_path, project_policy, tool_id=tool_id)
            connector_context: dict = {}
            if tool_id == "invoke_connector_operation":
                connector_context = build_connector_policy_context(active_config, arguments)
                arguments = connector_context["arguments"]
                if not connector_context.get("connector_enabled"):
                    raise PermissionError("Connecteur desactive.")
                if not connector_context.get("operation_enabled"):
                    raise PermissionError("Operation connecteur desactivee.")
                if connector_context.get("auth_status") == "missing":
                    raise PermissionError("Auth connecteur manquante.")
                if profile.id == "omega-research" and connector_context.get("action_category") != "read_only":
                    raise PermissionError("Omega Research autorise uniquement les operations connecteur read-only.")
            validate_browser_tool_request(active_config, tool_id, arguments)
            validate_desktop_tool_request(active_config, tool_id, arguments, active_window_title())
        except (PermissionError, ValueError) as exc:
            decision = {"action": "deny", "reason": str(exc), "risk_level": "critical", "redacted_arguments": arguments}
            self.durable.record_action(run_id, tool_id, arguments, decision, step_id=step.id)
            self.durable.fail_step(step.id, str(exc))
            if owns_run:
                self.durable.fail_run(run_id, str(exc))
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
            self._record_capability_usage(tool_id, "denied", run_id, session_id, error=str(exc))
            return ToolResult("denied", str(exc))
        budget_context = self.budgets.context(
            run_id=run_id,
            session_id=session_id,
            project_id=getattr(project, "id", None),
            agent_profile_id=getattr(profile, "id", None),
            connector_id=str(connector_context.get("connector_id") or "") or None,
        )
        action_category = str(connector_context.get("action_category") or classify_policy_action(tool_id, arguments))
        contextual_risk = classify_action_risk(
            tool_id,
            arguments,
            action_category=action_category,
            path_in_workspace=is_workspace_resource(active_config, tool_id, arguments),
        ).level
        risk_level = str(
            connector_context.get("risk_level")
            or max_risk_level(
                contextual_risk,
                tool.risk_level or tool.risk,
            )
        )
        budget_action = {
            "tool_name": tool_id,
            "arguments": arguments,
            "risk_level": risk_level,
            "action_category": action_category,
            "connector_id": str(connector_context.get("connector_id") or "") or None,
            "approval_granted": approval_id is not None,
            "skip_action_count": bool(budget_context.workflow_run_id),
        }
        budget_decision = self.budgets.check_before_action(budget_context, budget_action)
        enforce_budget_decision = self.config.governance_budgets_enforce or (
            self.config.governance_risk_governor_enabled and budget_decision.metric is None
        )
        if enforce_budget_decision and budget_decision.action in {"deny", "pause", "require_approval"}:
            decision_action = "require_approval" if budget_decision.action == "require_approval" else "deny"
            decision = {
                "action": decision_action,
                "reason": budget_decision.reason,
                "risk_level": budget_decision.risk_level,
                "action_category": budget_action["action_category"],
            }
            action = self.durable.record_action(run_id, tool_id, arguments, decision, step_id=step.id, budget_decision=budget_decision)
            if budget_decision.action == "pause":
                self.durable.complete_step(step.id, {"status": "budget_paused", "reason": budget_decision.reason})
                self.durable.pause_run_for_budget(run_id, budget_decision.reason)
                self._record_capability_usage(tool_id, "denied", run_id, session_id, error=budget_decision.reason, metadata={"budget": True})
                return ToolResult("budget_paused", budget_decision.reason)
            if budget_decision.action == "deny":
                self.durable.fail_step(step.id, budget_decision.reason)
                if owns_run:
                    self.durable.fail_run(run_id, budget_decision.reason)
                self._record_capability_usage(tool_id, "denied", run_id, session_id, error=budget_decision.reason, metadata={"budget": True})
                return ToolResult("denied", budget_decision.reason)
            approval = self.approvals.create(
                tool_id,
                arguments,
                risk=budget_decision.risk_level,
                session_id=session_id,
                reason=budget_decision.reason,
                action_id=action.id,
            )
            self.durable.complete_step(step.id, {"approval_id": approval.id, "action_id": action.id, "budget": True})
            self._record_capability_usage(tool_id, "approval_required", run_id, session_id, metadata={"approval_id": approval.id, "budget": True})
            return ToolResult("approval_required", "Approval requise par Budget & Risk Governor.", approval_id=approval.id)
        session = self.sessions.get_session(session_id)
        profile_requires_approval = _profile_requires_approval(profile, tool_id)
        session_policy_requires_approval = _session_requires_approval(session, tool.risk_level or tool.risk)
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
        connector_context = locals().get("connector_context", {})
        connector_requires_approval = bool(connector_context.get("requires_approval_default")) if tool_id == "invoke_connector_operation" else False
        connector_untrusted = str(connector_context.get("source_trust") or "local") in {"untrusted", "blocked"} if tool_id == "invoke_connector_operation" else False
        require_approval = (tool.requires_approval and active_config.require_approval) or browser_requires_approval or desktop_requires_approval or profile_requires_approval or session_policy_requires_approval or connector_requires_approval or connector_untrusted
        if active_config.workspace_full_access and tool_id in _WORKSPACE_FULL_ACCESS_TOOLS:
            require_approval = False
        policy_context = _session_policy_context(session)
        policy_context.update(
            {
                "session_id": session_id,
                "project_id": getattr(project, "id", None),
                "agent_profile_id": getattr(profile, "id", None),
            }
        )
        if connector_context:
            policy_context.update({key: value for key, value in connector_context.items() if key != "arguments"})
        decision = workspace_policy_decision(
            active_config,
            tool_id,
            arguments,
            require_approval=require_approval and approval_id is None,
            context=policy_context,
        )
        explicit_shadow_rule = any(bool(rule.get("shadow_required")) for rule in (decision.matched_rules or []))
        if decision.shadow_required and explicit_shadow_rule and not shadow_run_id:
            self.durable.record_action(run_id, tool_id, arguments, decision, step_id=step.id, budget_decision=budget_decision)
            self.durable.complete_step(step.id, {"status": "shadow_required", "reason": decision.reason})
            if owns_run:
                self.durable.pause_run(run_id)
            self.events.add(
                "policy.shadow_required",
                {"tool_name": tool_id, "run_id": run_id, "reason": decision.reason},
                session_id=session_id,
            )
            return ToolResult("shadow_required", "Shadow run requis avant exécution live.")
        action = self.durable.record_action(run_id, tool_id, arguments, decision, step_id=step.id, budget_decision=budget_decision)
        if decision.action == "deny":
            self.events.add("policy.denied", {"tool_name": tool_id, "run_id": run_id, "reason": decision.reason, "matched_rules": decision.matched_rules or []}, session_id=session_id)
            self.durable.fail_step(step.id, decision.reason)
            if owns_run:
                self.durable.fail_run(run_id, decision.reason)
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
            self._record_capability_usage(tool_id, "denied", run_id, session_id, error=decision.reason)
            return ToolResult("denied", decision.reason)
        if decision.action == "require_approval" and approval_id is None:
            self.events.add("policy.approval_required", {"tool_name": tool_id, "run_id": run_id, "reason": decision.reason, "matched_rules": decision.matched_rules or []}, session_id=session_id)
            approval_risk = "critical" if profile.policy.get("approval_mode") == "critical" else decision.risk_level
            approval = self.approvals.create(tool_id, arguments, risk=approval_risk, session_id=session_id, reason=decision.reason, action_id=action.id)
            self.durable.complete_step(step.id, {"approval_id": approval.id, "action_id": action.id})
            emit_reasoning_event(
                session_id or "",
                "reasoning.approval_required",
                "Approval requise",
                f"{tool_id} est bloqué jusqu'à validation utilisateur.",
                status="pending",
                metadata={"approval_id": approval.id, "tool_name": tool_id, "risk_level": approval_risk, "reason": decision.reason},
                config=self.config,
            )
            self._record_capability_usage(tool_id, "approval_required", run_id, session_id, metadata={"approval_id": approval.id})
            return ToolResult("approval_required", "Approval requise.", approval_id=approval.id)
        self.events.add("policy.allowed", {"tool_name": tool_id, "run_id": run_id, "reason": decision.reason, "matched_rules": decision.matched_rules or []}, session_id=session_id)
        handler = HANDLERS.get(tool_id)
        self.durable.create_checkpoint(
            run_id,
            f"before {tool_id}",
            checkpoint_state(
                self.config,
                run_id=run_id,
                session_id=session_id or "",
                current_step={"id": step.id, "type": "tool_call", "tool_name": tool_id},
                active_agent_profile_id=profile.id,
                project_id=getattr(project, "id", None),
                policy_context={"decision": decision.action, "reason": decision.reason, "risk_level": decision.risk_level},
                metadata={"phase": "before_tool"},
            ),
        )
        if tool_modifies_files(tool_id, arguments):
            paths = snapshot_paths_for_tool(tool_id, arguments)
            if paths:
                try:
                    self.durable.create_snapshot_for_paths(run_id, action.id, paths)
                except Exception as exc:
                    self.durable.mark_action_failed(action.id, str(exc))
                    self.durable.fail_step(step.id, str(exc))
                    if owns_run:
                        self.durable.fail_run(run_id, str(exc))
                    self._record_capability_usage(tool_id, "denied", run_id, session_id, error=str(exc))
                    return ToolResult("denied", str(exc))
        self.durable.mark_action_running(action.id)
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
                self.durable.mark_action_failed(action.id, str(exc))
                self.durable.fail_step(step.id, str(exc))
                if owns_run:
                    self.durable.fail_run(run_id, str(exc))
                self._record_capability_usage(tool_id, "failed", run_id, session_id, error=str(exc))
                return ToolResult("denied", str(exc))
            output = delegation.result or f"Delegation creee: {delegation.id}"
            self.durable.mark_action_completed(action.id, output)
            self.durable.complete_step(step.id, {"output": output})
            self.budgets.check_after_action(budget_context, budget_action, ToolResult("completed", output))
            if owns_run:
                self.durable.complete_run(run_id, output)
            self._record_capability_usage(tool_id, "completed", run_id, session_id)
            return ToolResult("completed", output)
        if handler is None:
            self.durable.mark_action_failed(action.id, "Handler tool introuvable.")
            self.durable.fail_step(step.id, "Handler tool introuvable.")
            if owns_run:
                self.durable.fail_run(run_id, "Handler tool introuvable.")
            self._record_capability_usage(tool_id, "failed", run_id, session_id, error="Handler tool introuvable.")
            return ToolResult("denied", "Handler tool introuvable.")
        self.events.add("tool.started", {"tool_name": tool_id, "run_id": run_id, "action_id": action.id, "step_id": step.id}, session_id=session_id)
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
            self.budgets.check_after_action(budget_context, budget_action, ToolResult("failed", str(exc)))
            self.durable.mark_action_failed(action.id, str(exc))
            self.durable.fail_step(step.id, str(exc))
            if owns_run:
                self.durable.fail_run(run_id, str(exc))
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
            self._record_capability_usage(tool_id, "failed", run_id, session_id, error=str(exc))
            return ToolResult("denied", str(exc))
        self.durable.mark_action_completed(action.id, output)
        self.durable.complete_step(step.id, {"output": output})
        self.budgets.check_after_action(budget_context, budget_action, ToolResult("completed", output))
        self.durable.create_checkpoint(
            run_id,
            f"after {tool_id}",
            checkpoint_state(
                self.config,
                run_id=run_id,
                session_id=session_id or "",
                current_step={"id": step.id, "type": "tool_call", "tool_name": tool_id},
                active_agent_profile_id=profile.id,
                project_id=getattr(project, "id", None),
                tool_observations=[{"tool_name": tool_id, "output": _summarize_tool_output(output)}],
                metadata={"phase": "after_tool"},
            ),
        )
        if owns_run:
            self.durable.complete_run(run_id, str(output))
        self.events.add("tool.completed", {"tool_name": tool_id, "run_id": run_id, "action_id": action.id, "step_id": step.id}, session_id=session_id)
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
        self._record_capability_usage(tool_id, "completed", run_id, session_id)
        return ToolResult("completed", output)

    def _call_shadow(
        self,
        tool_id: str,
        arguments: dict,
        *,
        session_id: str | None,
        shadow_workspace: Path | str | None,
        shadow_run_id: str | None,
    ) -> ToolResult:
        if not self.config.shadow_enabled:
            return ToolResult("denied", "Shadow execution disabled.", metadata={"simulation": True})
        if not shadow_workspace or not shadow_run_id:
            return ToolResult("denied", "Shadow workspace et shadow_run_id requis.", metadata={"simulation": True})
        candidate = Path(shadow_workspace).expanduser().resolve()
        controlled_root = (self.config.workspace / ".omega" / "shadow").resolve()
        try:
            candidate.relative_to(controlled_root)
        except ValueError:
            return ToolResult("denied", "Shadow workspace hors racine contrôlée.", metadata={"simulation": True})
        tool = self.registry.get(tool_id)
        if tool is None or not tool.enabled:
            return ToolResult("denied", "Tool introuvable ou désactivé.", metadata={"simulation": True})
        if tool_id == "invoke_connector_operation":
            requested_category = str(arguments.get("action_category") or "")
            if requested_category in {"reversible_write", "destructive_write", "external_side_effect", "system_sensitive"}:
                return ToolResult(
                    "shadow_skipped",
                    "Opération connecteur write simulée sans appel externe.",
                    metadata={"simulation": True, "external": True, "action_category": requested_category, "would_execute_live": False},
                )
            try:
                connector_context = build_connector_policy_context(self.config, arguments)
            except Exception as exc:
                return ToolResult("denied", str(exc), metadata={"simulation": True, "external": True})
            category = str(connector_context.get("action_category") or "read_only")
            return ToolResult(
                "shadow_skipped",
                "Opération connecteur simulée sans appel externe.",
                metadata={
                    "simulation": True,
                    "external": True,
                    "action_category": category,
                    "would_execute_live": category == "read_only",
                },
            )
        if tool_id.startswith(("browser_", "desktop_")) or tool_id in {"delegate_to_agent", "remember"}:
            return ToolResult(
                "shadow_skipped",
                "Action non locale simulée et non exécutée.",
                metadata={"simulation": True, "non_simulable": True},
            )
        if tool_id in {"git_add", "git_commit", "git_restore_file"}:
            return ToolResult(
                "shadow_skipped",
                "Écriture Git non exécutée en shadow.",
                metadata={"simulation": True, "non_simulable": True},
            )
        if tool_id == "run_shell" and not self.config.shadow_allow_shell_in_shadow:
            return ToolResult(
                "shadow_skipped",
                "Shell shadow désactivé par configuration.",
                metadata={"simulation": True, "non_simulable": True},
            )
        shadow_config = replace(
            self.config,
            workspace=candidate,
            require_approval=False,
            workspace_full_access=True,
            shell_full_access_in_workspace=bool(self.config.shadow_allow_shell_in_shadow),
            allow_delete_in_workspace=True,
            allow_git_write_in_workspace=False,
        )
        try:
            decision = workspace_policy_decision(
                shadow_config,
                tool_id,
                arguments,
                require_approval=False,
                context={"session_id": session_id, "source_trust": "local", "shadow_mode": True},
            )
            if decision.action == "deny":
                return ToolResult(
                    "denied",
                    decision.reason,
                    metadata={"simulation": True, "policy_decision": decision.action, "risk_level": decision.risk_level},
                )
            handler = HANDLERS.get(tool_id)
            if handler is None:
                return ToolResult("shadow_skipped", "Handler non simulable.", metadata={"simulation": True, "non_simulable": True})
            output = handler(shadow_config, arguments)
            refused = any(marker in str(output).lower() for marker in ("refusee:", "refusée:", "refuse:", "refusé:"))
            return ToolResult(
                "denied" if refused else "completed",
                str(output),
                metadata={
                    "simulation": True,
                    "shadow_run_id": shadow_run_id,
                    "policy_decision": decision.action,
                    "would_require_approval_live": decision.action == "require_approval",
                    "risk_level": decision.risk_level,
                },
            )
        except Exception as exc:
            return ToolResult("denied", str(exc), metadata={"simulation": True, "shadow_run_id": shadow_run_id})

    def _ensure_run_context(self, session_id: str | None, run_id: str | None, tool_id: str) -> tuple[str, str, bool]:
        if session_id is None:
            session_id = self.sessions.default_session_id()
        if run_id:
            return session_id, run_id, False
        run = self.durable.create_run(
            session_id,
            f"Tool call: {tool_id}",
            metadata={"source": "tool_broker", "tool_name": tool_id},
        )
        self.durable.start_run(run.id)
        return session_id, run.id, True

    def _record_capability_usage(self, tool_id: str, status: str, run_id: str | None, session_id: str | None, *, error: str | None = None, metadata: dict | None = None) -> None:
        self.capability_usage.record(f"tool:{tool_id}", status, run_id=run_id, session_id=session_id, error=error, metadata=metadata or {})


def _profile_requires_approval(profile, tool_id: str) -> bool:
    policy = profile.policy
    if policy.get("approval_mode") == "critical":
        return True
    if policy.get("all_sensitive_requires_approval") and tool_id in {"write_file", "append_file", "run_shell", "git_diff"}:
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


def _session_policy_context(session) -> dict:
    if session is None:
        return {"channel": "local", "source_trust": "local"}
    try:
        metadata = json.loads(session.metadata_json)
    except json.JSONDecodeError:
        metadata = {}
    channel = metadata.get("channel") or metadata.get("external_channel") or ("mobile" if metadata.get("mobile") else "local")
    source_trust = metadata.get("source_trust") or ("untrusted" if metadata.get("untrusted_input") else "local")
    return {"channel": channel, "source_trust": source_trust}


def _path_inside_workspace(workspace: Path, candidate: Path) -> bool:
    workspace_resolved = workspace.resolve()
    candidate_resolved = candidate.expanduser().resolve()
    try:
        return os.path.commonpath([str(workspace_resolved), str(candidate_resolved)]) == str(workspace_resolved)
    except ValueError:
        return False


def _normalize_tool_arguments(tool_id: str, arguments: dict) -> dict:
    if tool_id in {"list_files", "read_file", "write_file", "append_file", "delete_file", "create_directory", "delete_directory", "list_tree", "file_exists"}:
        if "relative_path" not in arguments and "path" in arguments:
            arguments["relative_path"] = arguments["path"]
    if tool_id in {"move_file", "copy_file"}:
        if "source_path" not in arguments and "source" in arguments:
            arguments["source_path"] = arguments["source"]
        if "destination_path" not in arguments and "destination" in arguments:
            arguments["destination_path"] = arguments["destination"]
        if "destination_path" not in arguments and "target" in arguments:
            arguments["destination_path"] = arguments["target"]
    return arguments
