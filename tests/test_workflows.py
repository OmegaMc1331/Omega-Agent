from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolResult
from omega_agent.storage.migrations import migrate
from omega_agent.workflows.workflow_runner import WorkflowRunner
from omega_agent.workflows.workflow_store import WorkflowStore
from omega_agent.workflows.workflow_templates import builtin_workflow_templates
from omega_agent.workflows.workflow_validator import WorkflowValidationError, validate_workflow


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=True,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        allow_git_write_in_workspace=False,
        db_path=tmp_path / "omega.db",
        evals_enabled=False,
    )


def simple_write_workflow() -> dict:
    return {
        "name": "Write workflow",
        "description": "Write a file through ToolBroker.",
        "version": "1.0",
        "steps": [
            {
                "id": "write",
                "type": "tool",
                "name": "Write file",
                "tool": "write_file",
                "arguments": {"relative_path": "workflow.txt", "content": "OK"},
            },
            {"id": "final", "type": "final", "name": "Final", "message": "done"},
        ],
    }


def test_workflow_migrations_are_idempotent(tmp_path: Path):
    config = cfg(tmp_path)
    migrate(config)
    migrate(config)
    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    assert {"workflows", "workflow_runs", "workflow_step_runs", "workflow_templates"}.issubset(tables)


def test_workflow_validation_accepts_templates_and_rejects_unknown_step(tmp_path: Path):
    config = cfg(tmp_path)
    for template in builtin_workflow_templates():
        validate_workflow(template["definition"], max_steps=config.workflows_max_steps)

    bad = {"name": "Bad", "steps": [{"id": "x", "type": "teleport"}]}
    try:
        validate_workflow(bad)
    except WorkflowValidationError as exc:
        assert "Unknown workflow step type" in str(exc)
    else:
        raise AssertionError("Unknown workflow step type was accepted.")


def test_workflow_run_uses_tool_broker_and_durable_runtime(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Workflow")
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow(simple_write_workflow())

    workflow_run = runner.run_workflow(workflow.id, session_id=session.id)

    assert workflow_run.status == "succeeded"
    assert (config.workspace / "workflow.txt").read_text(encoding="utf-8") == "OK"
    assert len(runner.store.list_step_runs(workflow_run.id)) == 2
    assert workflow_run.run_id
    actions = DurableRuntime(config).list_actions(workflow_run.run_id)
    assert [action.tool_name for action in actions] == ["write_file"]
    assert actions[0].status == "succeeded"


def test_shell_step_passes_through_tool_broker(tmp_path: Path):
    config = cfg(tmp_path)
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow(
        {
            "name": "Shell workflow",
            "steps": [
                {"id": "shell", "type": "shell", "name": "Shell", "command": "python --version", "on_error": "fail"},
                {"id": "final", "type": "final", "name": "Final", "message": "done"},
            ],
        }
    )

    workflow_run = runner.run_workflow(workflow.id)

    assert workflow_run.status == "succeeded"
    actions = DurableRuntime(config).list_actions(workflow_run.run_id)
    assert any(action.tool_name == "run_shell" for action in actions)


def test_approval_step_pauses_and_resume_after_approval(tmp_path: Path):
    config = cfg(tmp_path)
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow(
        {
            "name": "Approval workflow",
            "steps": [
                {"id": "approve", "type": "approval", "name": "Approve", "message": "Continue?"},
                {"id": "final", "type": "final", "name": "Final", "message": "done"},
            ],
        }
    )

    workflow_run = runner.run_workflow(workflow.id)

    assert workflow_run.status == "paused"
    approval = ApprovalsStore(config).list(status="pending")[0]
    ApprovalsStore(config).resolve(approval.id, True)
    resumed = runner.resume_workflow_run(workflow_run.id)

    assert resumed.status == "succeeded"
    steps = runner.store.list_step_runs(workflow_run.id)
    assert [step.status for step in steps] == ["succeeded", "succeeded"]


def test_failed_step_can_be_retried(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    runner = WorkflowRunner(config)
    calls = {"count": 0}

    def fake_call(tool_id, arguments, session_id=None, approval_id=None, run_id=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return ToolResult("denied", "temporary failure")
        return ToolResult("completed", "true")

    monkeypatch.setattr(runner.broker, "call", fake_call)
    workflow = runner.create_workflow(
        {
            "name": "Retry workflow",
            "steps": [
                {"id": "probe", "type": "tool", "name": "Probe", "tool": "file_exists", "arguments": {"relative_path": "x.txt"}},
                {"id": "final", "type": "final", "name": "Final", "message": "done"},
            ],
        }
    )

    failed = runner.run_workflow(workflow.id)
    retried = runner.retry_step(failed.id, "probe")

    assert failed.status == "failed"
    assert retried.status == "succeeded"


def test_cancel_workflow_run(tmp_path: Path):
    config = cfg(tmp_path)
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow(
        {
            "name": "Cancelable workflow",
            "steps": [{"id": "approve", "type": "approval", "name": "Approve", "message": "Continue?"}],
        }
    )
    workflow_run = runner.run_workflow(workflow.id)

    cancelled = runner.cancel_workflow_run(workflow_run.id)

    assert cancelled.status == "cancelled"


def test_workflow_endpoints(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    assert client.get("/api/workflows/templates").status_code == 200
    created = client.post("/api/workflows", json={"definition": simple_write_workflow()})
    assert created.status_code == 200
    workflow_id = created.json()["id"]
    run = client.post(f"/api/workflows/{workflow_id}/run", json={"input": {}})
    assert run.status_code == 200
    workflow_run_id = run.json()["id"]
    detail = client.get(f"/api/workflows/runs/{workflow_run_id}")
    assert detail.status_code == 200
    assert detail.json()["steps"]


def test_workflows_cli_templates_and_list(tmp_path: Path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace-cli"
    workspace.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "OMEGA_CONFIG_PATH": str(config_path),
            "OMEGA_DB_PATH": str(tmp_path / "cli.db"),
            "OMEGA_WORKSPACE": str(workspace),
            "OMEGA_WORKSPACE_FULL_ACCESS": "true",
            "OMEGA_REQUIRE_APPROVAL": "false",
            "OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE": "true",
        }
    )

    templates = subprocess.run([sys.executable, "-m", "omega_agent.main", "workflows", "templates"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30)
    listing = subprocess.run([sys.executable, "-m", "omega_agent.main", "workflows", "list"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30)

    assert templates.returncode == 0, templates.stderr + templates.stdout
    assert "Repo Health Check" in templates.stdout
    assert listing.returncode == 0, listing.stderr + listing.stdout


def test_git_status_does_not_escape_nested_workspace(tmp_path: Path):
    workspace = Path.cwd() / ".tmp" / f"git-ceiling-{uuid4().hex}"
    workspace.mkdir(parents=True)
    try:
        config = OmegaConfig(
            model="test",
            workspace=workspace,
            require_approval=False,
            workspace_full_access=True,
            shell_full_access_in_workspace=True,
            db_path=tmp_path / "omega.db",
            evals_enabled=False,
        )
        session = SessionsStore(config).create_session("Git ceiling")

        result = WorkflowRunner(config).broker.call("git_status", {}, session_id=session.id)

        assert result.status == "completed"
        assert "omega_agent" not in result.output
        assert "modified:" not in result.output
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
