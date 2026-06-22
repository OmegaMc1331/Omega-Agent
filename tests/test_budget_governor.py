import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.gateway.server import create_app
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.governance.budget_store import BudgetStore
from omega_agent.governance.quota_tracker import QuotaTracker
from omega_agent.governance.risk_governor import RiskGovernor
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.runtime.tools_registry import HANDLERS
from omega_agent.security.audit import run_security_audit
from omega_agent.workflows.workflow_runner import WorkflowRunner


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "workspace_full_access": True,
        "shell_full_access_in_workspace": True,
        "allow_delete_in_workspace": True,
        "db_path": tmp_path / "omega.db",
        "evals_enabled": False,
    }
    values.update(overrides)
    return OmegaConfig(**values)


def run_context(config: OmegaConfig):
    session = SessionsStore(config).create_session("Budget")
    runtime = DurableRuntime(config)
    run = runtime.create_run(session.id, "Budget test")
    runtime.start_run(run.id)
    return session, run


def set_limits(config: OmegaConfig, **limits):
    store = BudgetStore(config)
    profile = store.get_profile("default-local")
    store.update_profile(profile.id, {"limits": {**profile.limits, **limits}})


def test_default_budget_profiles_created(tmp_path: Path):
    profiles = BudgetStore(cfg(tmp_path)).list_profiles()

    assert {"Default Local", "Strict", "Developer Workspace", "Mobile"}.issubset({item.name for item in profiles})
    assert next(item for item in profiles if item.name == "Default Local").enabled is True


def test_max_tool_calls_enforced_and_run_paused(tmp_path: Path):
    config = cfg(tmp_path)
    set_limits(config, max_tool_calls=1)
    session, run = run_context(config)
    broker = ToolBroker(config)

    assert broker.call("list_files", {"relative_path": "."}, session_id=session.id, run_id=run.id).status == "completed"
    blocked = broker.call("list_files", {"relative_path": "."}, session_id=session.id, run_id=run.id)

    assert blocked.status == "budget_paused"
    assert DurableRuntime(config).get_run(run.id).status == "paused"
    assert "max_tool_calls" in DurableRuntime(config).get_run(run.id).error
    violations = BudgetStore(config).list_violations(run_id=run.id)
    assert violations[0].metric == "max_tool_calls"
    assert DurableRuntime(config).list_actions(run.id)[-1].budget_decision["action"] == "pause"


def test_shell_and_file_budgets_prevent_execution(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    set_limits(config, max_shell_commands=0, max_files_changed=0)
    session, run = run_context(config)
    calls = {"shell": 0, "write": 0}

    def fake_shell(active_config, arguments):
        calls["shell"] += 1
        return "shell"

    def fake_write(active_config, arguments):
        calls["write"] += 1
        return "write"

    monkeypatch.setitem(HANDLERS, "run_shell", fake_shell)
    monkeypatch.setitem(HANDLERS, "write_file", fake_write)
    broker = ToolBroker(config)

    shell = broker.call("run_shell", {"command": "python --version"}, session_id=session.id, run_id=run.id)
    DurableRuntime(config).resume_run(run.id)
    write = broker.call("write_file", {"relative_path": "blocked.txt", "content": "NO"}, session_id=session.id, run_id=run.id)

    assert shell.status == "budget_paused"
    assert write.status == "budget_paused"
    assert calls == {"shell": 0, "write": 0}
    assert not (config.workspace / "blocked.txt").exists()


def test_risk_governor_enforces_max_and_system_sensitive(tmp_path: Path):
    config = cfg(tmp_path, governance_risk_governor_default_max_risk="medium")
    governor = RiskGovernor(config)

    above_limit = governor.evaluate(risk_level="high", action_category="reversible_write", max_risk_level="medium")
    critical = governor.evaluate(risk_level="critical", action_category="system_sensitive", max_risk_level="critical")

    assert above_limit.action == "require_approval"
    assert critical.action == "deny"


def test_tool_broker_does_not_execute_critical_action(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    session, run = run_context(config)
    broker = ToolBroker(config)
    original = broker.registry.get("list_files")
    calls = {"count": 0}

    monkeypatch.setattr(broker.registry, "get", lambda tool_id: replace(original, risk="critical", risk_level="critical"))
    monkeypatch.setitem(HANDLERS, "list_files", lambda active_config, arguments: calls.update(count=calls["count"] + 1) or "executed")

    result = broker.call("list_files", {"relative_path": "."}, session_id=session.id, run_id=run.id)

    assert result.status == "denied"
    assert calls["count"] == 0
    assert "risk critical exceeds maximum high" in result.output.lower()


def test_warning_at_eighty_percent_and_usage_persisted(tmp_path: Path):
    config = cfg(tmp_path)
    set_limits(config, max_tool_calls=5)
    session, run = run_context(config)
    broker = ToolBroker(config)

    for _ in range(4):
        assert broker.call("list_files", {"relative_path": "."}, session_id=session.id, run_id=run.id).status == "completed"

    usage = next(item for item in QuotaTracker(config).list(run_id=run.id) if item.metric == "max_tool_calls")
    assert usage.used_value == 4
    assert usage.status == "warning"


def test_workflow_step_pauses_when_action_budget_exceeded(tmp_path: Path):
    config = cfg(tmp_path)
    set_limits(config, max_actions=0)
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow({"name": "Budget workflow", "steps": [{"id": "final", "type": "final", "name": "Final", "message": "done"}]})

    workflow_run = runner.run_workflow(workflow.id)

    assert workflow_run.status == "paused"
    assert DurableRuntime(config).get_run(workflow_run.run_id).status == "paused"
    assert BudgetStore(config).list_violations(workflow_run_id=workflow_run.id)[0].metric == "max_actions"


def test_budget_endpoints_and_simulation(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    profiles = client.get("/api/budgets/profiles")
    assert profiles.status_code == 200
    created = client.post(
        "/api/budgets/profiles",
        json={"name": "Project tight", "scope_type": "project", "scope_id": "default", "limits": {"max_tool_calls": 2, "max_risk_level": "medium"}},
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]
    assert client.get(f"/api/budgets/profiles/{profile_id}").status_code == 200
    assert client.patch(f"/api/budgets/profiles/{profile_id}", json={"enabled": False}).status_code == 200
    assert client.get("/api/budgets/effective").status_code == 200
    simulation = client.post("/api/budgets/simulate", json={"action": {"tool_name": "system_exec", "risk_level": "critical", "action_category": "system_sensitive"}})
    assert simulation.status_code == 200
    assert simulation.json()["decision"]["action"] == "deny"
    assert client.get("/api/budgets/usage").status_code == 200
    assert client.get("/api/budgets/violations").status_code == 200


def test_security_audit_warns_when_budgets_disabled(tmp_path: Path):
    config = cfg(tmp_path, governance_budgets_enabled=False, governance_budgets_enforce=False)

    report = run_security_audit(config)

    finding = next(item for item in report.findings if item.area == "governance")
    assert finding.severity == "high"
    assert "disabled" in finding.finding.lower()


def test_budget_cli(tmp_path: Path):
    config_path = tmp_path / "config.json"
    save_config(
        {
            "workspace": {"path": str(tmp_path / "workspace"), "full_access": True},
            "paths": {"db_path": str(tmp_path / "omega.db"), "skills_dir": str(tmp_path / "skills"), "plugins_dir": str(tmp_path / "plugins")},
            "evals": {"enabled": False},
        },
        config_path,
    )
    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}
    root = Path(__file__).resolve().parents[1]

    profiles = subprocess.run([sys.executable, "-m", "omega_agent.main", "budgets", "profiles"], cwd=root, env=env, text=True, capture_output=True, timeout=60)
    doctor = subprocess.run([sys.executable, "-m", "omega_agent.main", "budgets", "doctor"], cwd=root, env=env, text=True, capture_output=True, timeout=60)

    assert profiles.returncode == 0, profiles.stdout + profiles.stderr
    assert "Default Local" in profiles.stdout
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert "budgets enabled and enforced" in doctor.stdout
