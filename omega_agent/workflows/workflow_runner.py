from __future__ import annotations

import json
import time
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.runtime.approvals import Approval, ApprovalsStore
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker, ToolResult
from omega_agent.security.redaction import redact
from omega_agent.workflows.workflow_models import Workflow, WorkflowRun, WorkflowStepRun
from omega_agent.workflows.workflow_store import WorkflowStore
from omega_agent.workflows.workflow_validator import validate_workflow


class WorkflowRunner:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = WorkflowStore(config)
        self.durable = DurableRuntime(config)
        self.sessions = SessionsStore(config)
        self.approvals = ApprovalsStore(config)
        self.events = EventsStore(config)
        self.broker = ToolBroker(config)
        self.budgets = BudgetEnforcer(config)

    def create_workflow(self, definition: dict[str, Any], *, enabled: bool = True, metadata: dict[str, Any] | None = None) -> Workflow:
        normalized = self.validate_workflow(definition)
        return self.store.create_workflow(normalized, enabled=enabled, metadata=metadata)

    def validate_workflow(self, definition: dict[str, Any]) -> dict[str, Any]:
        return validate_workflow(
            definition,
            max_steps=self.config.workflows_max_steps,
            allow_nested_workflows=self.config.workflows_allow_nested_workflows,
        )

    def run_workflow(
        self,
        workflow_id: str,
        input: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        shadow_run_id: str | None = None,
    ) -> WorkflowRun:
        if not self.config.workflows_enabled:
            raise ValueError("Workflows disabled by configuration.")
        workflow = self.store.require_workflow(workflow_id)
        if not workflow.enabled:
            raise ValueError("Workflow disabled.")
        recommendation = self.shadow_recommendation(workflow.id)
        if recommendation["required"] and not shadow_run_id:
            raise ValueError("Shadow run requis avant ce workflow destructif.")
        session_id = session_id or self.sessions.default_session_id()
        durable_run = self.durable.create_run(
            session_id,
            f"Workflow: {workflow.name}",
            metadata={
                "source": "workflow",
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "shadow_run_id": shadow_run_id,
                "shadow_recommended": recommendation["recommended"],
            },
        )
        self.durable.start_run(durable_run.id)
        workflow_run = self.store.create_run(
            workflow.id,
            durable_run.id,
            input=input or {},
            metadata={"session_id": session_id, "shadow_run_id": shadow_run_id, "shadow_recommended": recommendation["recommended"]},
        )
        self.events.add("workflow.started", {"workflow_id": workflow.id, "workflow_run_id": workflow_run.id, "run_id": durable_run.id}, session_id=session_id)
        return self._execute_loop(workflow_run.id)

    def shadow_recommendation(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.store.require_workflow(workflow_id)
        steps = list(workflow.definition.get("steps") or [])
        destructive = any(_is_destructive_workflow_step(step) for step in steps)
        over_threshold = len(steps) > max(0, int(self.config.shadow_require_for_workflows_over_steps))
        required = bool(self.config.shadow_enabled and self.config.shadow_require_for_high_risk and destructive)
        return {
            "required": required,
            "recommended": required or over_threshold,
            "destructive": destructive,
            "step_count": len(steps),
            "threshold": self.config.shadow_require_for_workflows_over_steps,
        }

    def pause_workflow_run(self, workflow_run_id: str) -> WorkflowRun:
        workflow_run = self.store.require_run(workflow_run_id)
        self.store.update_run(workflow_run_id, status="paused")
        if workflow_run.run_id:
            self.durable.pause_run(workflow_run.run_id)
        self.events.add("workflow.paused", {"workflow_run_id": workflow_run_id, "run_id": workflow_run.run_id}, session_id=self._session_id(workflow_run))
        return self.store.require_run(workflow_run_id)

    def resume_workflow_run(self, workflow_run_id: str) -> WorkflowRun:
        workflow_run = self.store.require_run(workflow_run_id)
        if workflow_run.status == "cancelled":
            return workflow_run
        if workflow_run.run_id:
            durable = self.durable.get_run(workflow_run.run_id)
            if durable and durable.status in {"paused", "needs_approval"}:
                self.durable.resume_run(workflow_run.run_id)
        self.store.update_run(workflow_run_id, status="running", started=True)
        self.events.add("workflow.resumed", {"workflow_run_id": workflow_run_id, "run_id": workflow_run.run_id}, session_id=self._session_id(workflow_run))
        return self._execute_loop(workflow_run_id)

    def cancel_workflow_run(self, workflow_run_id: str) -> WorkflowRun:
        workflow_run = self.store.require_run(workflow_run_id)
        self.store.update_run(workflow_run_id, status="cancelled", completed=True, error="cancelled")
        if workflow_run.run_id:
            self.durable.cancel_run(workflow_run.run_id)
        self.events.add("workflow.cancelled", {"workflow_run_id": workflow_run_id, "run_id": workflow_run.run_id}, session_id=self._session_id(workflow_run))
        return self.store.require_run(workflow_run_id)

    def retry_step(self, workflow_run_id: str, step_id: str) -> WorkflowRun:
        workflow_run = self.store.require_run(workflow_run_id)
        workflow = self.store.require_workflow(workflow_run.workflow_id)
        definition = self.validate_workflow(workflow.definition)
        step_index, step_definition = _find_step(definition, step_id)
        step_run = self.store.get_step_run_by_step_id(workflow_run_id, step_id) or self.store.create_step_run(workflow_run_id, step_index, step_definition)
        self.store.update_run(workflow_run_id, status="running", current_step_index=step_index, started=True, error=None)
        self.events.add("workflow.resumed", {"workflow_run_id": workflow_run_id, "retry_step_id": step_id}, session_id=self._session_id(workflow_run))
        outcome = self._execute_step(workflow, workflow_run_id, step_index, step_definition, step_run, force=True)
        if outcome == "paused":
            return self.store.require_run(workflow_run_id)
        if outcome == "failed":
            return self.store.require_run(workflow_run_id)
        self.store.update_run(workflow_run_id, current_step_index=step_index + 1)
        return self._execute_loop(workflow_run_id)

    def get_workflow_run_status(self, workflow_run_id: str) -> dict[str, Any]:
        workflow_run = self.store.require_run(workflow_run_id)
        return {
            "workflow_run": workflow_run.as_api(),
            "steps": [step.as_api() for step in self.store.list_step_runs(workflow_run_id)],
            "durable_run": self.durable.get_run(workflow_run.run_id).as_api() if workflow_run.run_id and self.durable.get_run(workflow_run.run_id) else None,
        }

    def _execute_loop(self, workflow_run_id: str) -> WorkflowRun:
        workflow_run = self.store.require_run(workflow_run_id)
        workflow = self.store.require_workflow(workflow_run.workflow_id)
        definition = self.validate_workflow(workflow.definition)
        steps: list[dict[str, Any]] = list(definition["steps"])
        started_at = time.monotonic()
        session_id = self._session_id(workflow_run)
        self.store.update_run(workflow_run_id, status="running", started=True)
        outputs: dict[str, Any] = {}
        for completed_step in self.store.list_step_runs(workflow_run_id):
            if completed_step.output is not None:
                outputs[completed_step.step_id] = completed_step.output

        for index in range(max(0, workflow_run.current_step_index), len(steps)):
            workflow_run = self.store.require_run(workflow_run_id)
            if workflow_run.status == "cancelled":
                return workflow_run
            if time.monotonic() - started_at > max(1, self.config.workflows_max_duration_seconds):
                return self._fail_workflow(workflow_run_id, "Workflow timed out.")
            step_definition = steps[index]
            step_run = self.store.get_step_run_by_step_id(workflow_run_id, step_definition["id"]) or self.store.create_step_run(workflow_run_id, index, step_definition)
            if step_run.status == "succeeded" and index < workflow_run.current_step_index:
                continue
            outcome = self._execute_step(workflow, workflow_run_id, index, step_definition, step_run, context={"outputs": outputs})
            step_run = self.store.get_step_run(step_run.id) or step_run
            if step_run.output is not None:
                outputs[step_definition["id"]] = step_run.output
            if outcome == "paused":
                return self.store.require_run(workflow_run_id)
            if outcome == "failed":
                return self.store.require_run(workflow_run_id)
            self.store.update_run(workflow_run_id, current_step_index=index + 1)

        final_output = {"message": "Workflow completed.", "step_outputs": outputs}
        workflow_run = self.store.update_run(workflow_run_id, status="succeeded", output=final_output, completed=True)
        if workflow_run.run_id:
            self.durable.complete_run(workflow_run.run_id, str(final_output.get("message") or "Workflow completed."))
        self.events.add("workflow.completed", {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "run_id": workflow_run.run_id}, session_id=session_id)
        return workflow_run

    def _execute_step(
        self,
        workflow: Workflow,
        workflow_run_id: str,
        step_index: int,
        step_definition: dict[str, Any],
        step_run: WorkflowStepRun,
        *,
        context: dict[str, Any] | None = None,
        force: bool = False,
    ) -> str:
        workflow_run = self.store.require_run(workflow_run_id)
        session_id = self._session_id(workflow_run)
        metadata = dict(step_run.metadata)
        if step_run.status == "waiting_approval" and not force:
            approval_id = str((step_run.output or {}).get("approval_id") or metadata.get("approval_id") or "")
            approval = self._approval_by_id(approval_id) if approval_id else None
            if approval is None or approval.status == "pending":
                self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index)
                return "paused"
            if approval.status == "rejected":
                self.store.update_step_run(step_run.id, status="failed", error="Approval rejected.", completed=True)
                self._fail_workflow(workflow_run_id, "Approval rejected.")
                return "failed"
            metadata["approved_at"] = approval.resolved_at
            if step_definition["type"] == "tool" and metadata.get("resume_tool_after_approval"):
                result = self.broker.call(
                    str(step_definition["tool"]),
                    _render_arguments(step_definition.get("arguments") or {}, workflow_run.input, context or {}),
                    session_id=session_id,
                    approval_id=approval_id,
                    run_id=workflow_run.run_id,
                )
                return self._finish_tool_result(workflow, workflow_run_id, step_run, step_definition, result, metadata)
            if step_definition["type"] == "shell" and metadata.get("resume_tool_after_approval"):
                result = self.broker.call(
                    "run_shell",
                    {
                        "command": _render_string(str(step_definition.get("command") or ""), workflow_run.input, context or {}),
                        "cwd": step_definition.get("cwd", "."),
                        "timeout_seconds": int(step_definition.get("timeout_seconds") or 60),
                    },
                    session_id=session_id,
                    approval_id=approval_id,
                    run_id=workflow_run.run_id,
                )
                return self._finish_tool_result(workflow, workflow_run_id, step_run, step_definition, result, metadata)
            self.store.update_step_run(step_run.id, status="succeeded", output={"approval_id": approval_id, "status": approval.status}, completed=True, metadata=metadata)
            return "succeeded"

        budget_context = self.budgets.context(
            run_id=workflow_run.run_id,
            workflow_run_id=workflow_run_id,
            workflow_id=workflow.id,
            session_id=session_id,
        )
        budget_decision = self.budgets.check_before_action(
            budget_context,
            {
                "workflow_step": True,
                "tool_name": "",
                "action_category": "read_only",
                "risk_level": str(step_definition.get("risk_level") or "low"),
            },
        )
        if self.config.governance_budgets_enforce and budget_decision.action in {"pause", "deny", "require_approval"}:
            self.store.update_step_run(step_run.id, status="pending", error=budget_decision.reason, metadata={**metadata, "budget_decision": budget_decision.as_api()})
            self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index, error=budget_decision.reason)
            if workflow_run.run_id:
                self.durable.pause_run_for_budget(workflow_run.run_id, budget_decision.reason)
            self.events.add(
                "workflow.paused",
                {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "reason": budget_decision.reason, "budget": True},
                session_id=session_id,
            )
            return "paused"
        self.store.update_run(workflow_run_id, status="running", current_step_index=step_index, started=True)
        self.store.update_step_run(step_run.id, status="running", started=True, metadata=metadata)
        self.events.add(
            "workflow.step.started",
            {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "step_index": step_index},
            session_id=session_id,
        )
        durable_step = None
        if workflow_run.run_id:
            durable_type = "approval" if step_definition["type"] == "approval" else "reasoning"
            durable_step = self.durable.append_step(
                workflow_run.run_id,
                durable_type,
                f"Workflow step: {step_definition.get('name') or step_definition['id']}",
                input={"workflow_run_id": workflow_run_id, "workflow_step_id": step_definition["id"], "type": step_definition["type"]},
                status="running",
            )
        attempts = 0
        max_attempts = max(1, int(step_definition.get("retries") or 0) + 1)
        while attempts < max_attempts:
            attempts += 1
            try:
                result = self._execute_step_body(workflow_run, step_definition, session_id, context or {})
                if result.get("status") == "paused":
                    if (result.get("output") or {}).get("budget"):
                        reason = str((result.get("output") or {}).get("message") or "Workflow paused by budget.")
                        self.store.update_step_run(step_run.id, status="pending", output=result.get("output") or {}, error=reason, completed=False, metadata={**metadata, "budget": True})
                        self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index, error=reason)
                        if workflow_run.run_id:
                            self.durable.pause_run_for_budget(workflow_run.run_id, reason)
                        if durable_step:
                            self.durable.complete_step(durable_step.id, result.get("output") or {})
                        return "paused"
                    metadata.update(result.get("metadata") or {})
                    self.store.update_step_run(step_run.id, status="waiting_approval", output=result.get("output") or {}, completed=False, metadata=metadata)
                    self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index)
                    if workflow_run.run_id and step_definition["type"] == "approval":
                        self.durable.pause_run(workflow_run.run_id)
                    if durable_step:
                        self.durable.complete_step(durable_step.id, result.get("output") or {})
                    self.events.add(
                        "workflow.paused",
                        {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "reason": "approval_required"},
                        session_id=session_id,
                    )
                    return "paused"
                if result.get("status") == "failed":
                    raise RuntimeError(str(result.get("error") or "Workflow step failed."))
                output = result.get("output")
                self.store.update_step_run(step_run.id, status="succeeded", output=output if isinstance(output, dict) else {"output": output}, completed=True, metadata=metadata)
                if durable_step:
                    self.durable.complete_step(durable_step.id, {"output": output})
                self.events.add(
                    "workflow.step.completed",
                    {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "step_index": step_index},
                    session_id=session_id,
                )
                self.budgets.record_usage(budget_context, "max_actions", 1, metadata={"workflow_step_id": step_definition["id"]})
                return "succeeded"
            except Exception as exc:
                if attempts < max_attempts and step_definition.get("on_error") == "retry":
                    retry_budget = self.budgets.check_metric(budget_context, "max_retries")
                    if retry_budget.action in {"pause", "deny", "require_approval"}:
                        reason = retry_budget.reason
                        self.store.update_step_run(step_run.id, status="pending", error=reason, metadata={**metadata, "budget": True})
                        self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index, error=reason)
                        if workflow_run.run_id:
                            self.durable.pause_run_for_budget(workflow_run.run_id, reason)
                        return "paused"
                    self.budgets.record_usage(budget_context, "max_retries", 1, metadata={"workflow_step_id": step_definition["id"]})
                    continue
                mode = str(step_definition.get("on_error") or "fail")
                if mode == "continue":
                    output = {"continued_after_error": True, "error": str(exc)}
                    self.store.update_step_run(step_run.id, status="skipped", output=output, error=str(exc), completed=True, metadata=metadata)
                    if durable_step:
                        self.durable.complete_step(durable_step.id, output)
                    self.events.add(
                        "workflow.step.failed",
                        {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "continued": True, "error": str(exc)},
                        session_id=session_id,
                    )
                    return "succeeded"
                if mode == "ask_user":
                    approval = self.approvals.create(
                        "workflow_step_retry",
                        {"workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "error": str(exc)},
                        risk="medium",
                        session_id=session_id,
                        reason=f"Workflow step failed: {exc}",
                        action_type="workflow",
                    )
                    self.store.update_step_run(step_run.id, status="waiting_approval", output={"approval_id": approval.id, "error": str(exc)}, error=str(exc), metadata={"approval_id": approval.id})
                    self.store.update_run(workflow_run_id, status="paused", current_step_index=step_index)
                    return "paused"
                self.store.update_step_run(step_run.id, status="failed", error=str(exc), completed=True, metadata=metadata)
                if durable_step:
                    self.durable.fail_step(durable_step.id, str(exc))
                self.events.add(
                    "workflow.step.failed",
                    {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"], "error": str(exc)},
                    session_id=session_id,
                )
                self._fail_workflow(workflow_run_id, str(exc))
                return "failed"
        return "failed"

    def _execute_step_body(self, workflow_run: WorkflowRun, step: dict[str, Any], session_id: str, context: dict[str, Any]) -> dict[str, Any]:
        step_type = step["type"]
        if step_type == "tool":
            result = self.broker.call(
                str(step["tool"]),
                _render_arguments(step.get("arguments") or {}, workflow_run.input, context),
                session_id=session_id,
                run_id=workflow_run.run_id,
            )
            if result.status == "approval_required":
                return {
                    "status": "paused",
                    "output": {"approval_id": result.approval_id, "status": result.status, "message": result.output},
                    "metadata": {"approval_id": result.approval_id, "resume_tool_after_approval": True},
                }
            return self._tool_result_payload(result)
        if step_type == "shell":
            result = self.broker.call(
                "run_shell",
                {
                    "command": _render_string(str(step.get("command") or ""), workflow_run.input, context),
                    "cwd": step.get("cwd", "."),
                    "timeout_seconds": int(step.get("timeout_seconds") or 60),
                },
                session_id=session_id,
                run_id=workflow_run.run_id,
            )
            if result.status == "approval_required":
                return {
                    "status": "paused",
                    "output": {"approval_id": result.approval_id, "status": result.status, "message": result.output},
                    "metadata": {"approval_id": result.approval_id, "resume_tool_after_approval": True},
                }
            return self._tool_result_payload(result)
        if step_type == "approval":
            approval = self.approvals.create(
                "workflow_step",
                {"workflow_run_id": workflow_run.id, "step_id": step["id"], "message": step["message"]},
                risk=str(step.get("risk_level") or "medium"),
                session_id=session_id,
                reason=str(step["message"]),
                action_type="workflow",
            )
            return {
                "status": "paused",
                "output": {"approval_id": approval.id, "message": step["message"]},
                "metadata": {"approval_id": approval.id},
            }
        if step_type == "condition":
            matched = _condition_matches(str(step.get("expression") or ""), workflow_run.input, context)
            return {"status": "succeeded", "output": {"matched": matched, "next": step.get("if_true") if matched else step.get("if_false")}}
        if step_type == "wait":
            seconds = max(0, min(int(step.get("seconds") or 0), 1))
            if seconds:
                time.sleep(seconds)
            return {"status": "succeeded", "output": {"waited_seconds": seconds}}
        if step_type == "memory":
            operation = str(step.get("operation") or "search")
            if operation in {"remember", "create"}:
                result = self.broker.call("remember", {"content": str(step.get("content") or ""), "tags": str(step.get("tags") or "workflow")}, session_id=session_id, run_id=workflow_run.run_id)
            else:
                result = self.broker.call("search_memory", {"query": str(step.get("query") or "")}, session_id=session_id, run_id=workflow_run.run_id)
            return self._tool_result_payload(result)
        if step_type == "agent":
            return {"status": "succeeded", "output": {"message": "Agent step recorded for future orchestration.", "prompt": redact(str(step.get("prompt") or step.get("message") or ""))}}
        if step_type == "workflow":
            if not self.config.workflows_allow_nested_workflows:
                return {"status": "failed", "error": "Nested workflows disabled."}
            nested = self.run_workflow(str(step["workflow_id"]), input=workflow_run.input, session_id=session_id)
            return {"status": "succeeded", "output": nested.as_api()}
        if step_type == "final":
            return {"status": "succeeded", "output": {"message": _render_string(str(step.get("message") or "Workflow completed."), workflow_run.input, context)}}
        return {"status": "failed", "error": f"Unsupported step type: {step_type}"}

    def _tool_result_payload(self, result: ToolResult) -> dict[str, Any]:
        if result.status == "budget_paused":
            return {"status": "paused", "output": {"status": result.status, "message": result.output, "budget": True}}
        if result.status in {"denied", "failed"}:
            return {"status": "failed", "error": result.output}
        return {"status": "succeeded", "output": {"status": result.status, "output": result.output, "approval_id": result.approval_id}}

    def _finish_tool_result(self, workflow: Workflow, workflow_run_id: str, step_run: WorkflowStepRun, step_definition: dict[str, Any], result: ToolResult, metadata: dict[str, Any]) -> str:
        payload = self._tool_result_payload(result)
        if payload["status"] == "failed":
            self.store.update_step_run(step_run.id, status="failed", error=str(payload["error"]), completed=True, metadata=metadata)
            self._fail_workflow(workflow_run_id, str(payload["error"]))
            return "failed"
        self.store.update_step_run(step_run.id, status="succeeded", output=payload["output"], completed=True, metadata=metadata)
        self.events.add(
            "workflow.step.completed",
            {"workflow_id": workflow.id, "workflow_run_id": workflow_run_id, "step_id": step_definition["id"]},
            session_id=self._session_id(self.store.require_run(workflow_run_id)),
        )
        return "succeeded"

    def _fail_workflow(self, workflow_run_id: str, error: str) -> WorkflowRun:
        workflow_run = self.store.update_run(workflow_run_id, status="failed", error=error, completed=True)
        if workflow_run.run_id:
            durable = self.durable.get_run(workflow_run.run_id)
            if durable and durable.status not in {"failed", "succeeded", "cancelled"}:
                self.durable.fail_run(workflow_run.run_id, error)
        self.events.add("workflow.failed", {"workflow_run_id": workflow_run_id, "run_id": workflow_run.run_id, "error": redact(str(error))}, session_id=self._session_id(workflow_run))
        return workflow_run

    def _approval_by_id(self, approval_id: str) -> Approval | None:
        return next((approval for approval in self.approvals.list() if approval.id == approval_id), None)

    def _session_id(self, workflow_run: WorkflowRun) -> str | None:
        value = workflow_run.metadata.get("session_id")
        return str(value) if value else None


def _find_step(definition: dict[str, Any], step_id: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(definition.get("steps") or []):
        if step.get("id") == step_id:
            return index, step
    raise ValueError("Workflow step introuvable.")


def _render_arguments(arguments: dict[str, Any], workflow_input: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {key: _render_value(value, workflow_input, context) for key, value in arguments.items()}


def _render_value(value: Any, workflow_input: dict[str, Any], context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, workflow_input, context)
    if isinstance(value, list):
        return [_render_value(item, workflow_input, context) for item in value]
    if isinstance(value, dict):
        return _render_arguments(value, workflow_input, context)
    return value


def _render_string(value: str, workflow_input: dict[str, Any], context: dict[str, Any]) -> str:
    result = value
    for key, item in workflow_input.items():
        result = result.replace("{{input." + str(key) + "}}", str(item))
    outputs = context.get("outputs") if isinstance(context, dict) else {}
    if isinstance(outputs, dict):
        for step_id, output in outputs.items():
            result = result.replace("{{steps." + str(step_id) + ".output}}", _compact_json(output))
    return result


def _compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _condition_matches(expression: str, workflow_input: dict[str, Any], context: dict[str, Any]) -> bool:
    lowered = expression.strip().lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0", ""}:
        return False
    if lowered.startswith("input."):
        key = expression.split(".", 1)[1]
        return bool(workflow_input.get(key))
    if "==" in expression:
        left, right = [part.strip().strip("'\"") for part in expression.split("==", 1)]
        if left.startswith("input."):
            return str(workflow_input.get(left.split(".", 1)[1], "")) == right
    return False


def _is_destructive_workflow_step(step: dict[str, Any]) -> bool:
    if str(step.get("type") or "") == "tool":
        return str(step.get("tool") or "") in {"delete_file", "delete_directory", "move_file"}
    if str(step.get("type") or "") == "shell":
        command = str(step.get("command") or "").lower()
        return any(fragment in command for fragment in ("del ", "erase ", "rmdir ", "remove-item", "rm "))
    return False
