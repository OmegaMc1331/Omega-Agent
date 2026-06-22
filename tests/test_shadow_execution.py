import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.gateway.server import create_app
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.policy_simulator import PolicySimulator
from omega_agent.shadow.shadow_runner import ShadowRunner
from omega_agent.shadow.shadow_workspace import ShadowWorkspace
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
        "shadow_enabled": True,
    }
    values.update(overrides)
    return OmegaConfig(**values)


def create_and_run(config: OmegaConfig, objective: str = "crée un fichier test-shadow.txt avec OK"):
    runner = ShadowRunner(config)
    created = runner.create_shadow_run(objective)
    return runner, runner.run_shadow(created["id"])


def test_shadow_tables_and_workspace_created(tmp_path: Path):
    config = cfg(tmp_path)
    runner = ShadowRunner(config)
    item = runner.create_shadow_run("crée un fichier test-shadow.txt avec OK")

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    result = runner.run_shadow(item["id"])

    assert {"shadow_runs", "shadow_steps", "shadow_promotions", "shadow_live_comparisons"}.issubset(tables)
    assert ShadowWorkspace(config, item["id"]).workspace.exists()
    assert result["status"] == "succeeded"


def test_shadow_write_does_not_modify_real_workspace_and_diff_detects_creation(tmp_path: Path):
    config = cfg(tmp_path)
    runner, result = create_and_run(config)

    assert not (config.workspace / "test-shadow.txt").exists()
    assert (ShadowWorkspace(config, result["id"]).workspace / "test-shadow.txt").read_text(encoding="utf-8") == "OK\n"
    assert result["predicted_diff"]["created"][0]["path"] == "test-shadow.txt"
    assert result["predicted_diff"]["summary"].startswith("1 créé")
    assert result["estimated_cost"]["estimated_tokens"] == 0
    assert result["risk_report"]["invariants"]["checks"]["real_workspace_unchanged"]["passed"] is True


def test_external_write_is_skipped_and_never_executed(tmp_path: Path):
    config = cfg(tmp_path)
    plan = {
        "version": "shadow-plan.v1",
        "objective": "external write",
        "steps": [
            {
                "index": 0,
                "name": "External write",
                "type": "tool",
                "tool_name": "invoke_connector_operation",
                "arguments": {
                    "connector_id": "missing",
                    "operation_id": "write",
                    "action_category": "external_side_effect",
                },
                "action_category": "external_side_effect",
                "risk_level": "high",
                "simulable": True,
            }
        ],
    }
    runner = ShadowRunner(config)
    created = runner.create_shadow_run("external write", plan=plan)
    result = runner.run_shadow(created["id"])

    assert result["status"] == "succeeded"
    assert result["steps"][0]["status"] == "skipped"
    assert result["risk_report"]["external_calls"] == 1
    assert result["risk_report"]["recommendation"] == "require_approval"


def test_risk_report_and_policy_simulator_require_shadow_for_destructive_action(tmp_path: Path):
    config = cfg(tmp_path)
    (config.workspace / "remove-me.txt").write_text("before", encoding="utf-8")
    runner, result = create_and_run(config, "supprime le fichier remove-me.txt")
    simulation = PolicySimulator(config).simulate_policy(
        {"tool_name": "delete_file", "arguments": {"relative_path": "remove-me.txt"}},
        store=False,
    )

    assert (config.workspace / "remove-me.txt").exists()
    assert result["risk_report"]["files_deleted"] == 1
    assert result["risk_report"]["risk_level"] == "high"
    assert result["risk_report"]["recommendation"] == "require_approval"
    assert simulation["shadow_required"] is True


def test_high_risk_promotion_requires_approval_then_creates_live_run(tmp_path: Path):
    config = cfg(tmp_path)
    runner, shadow = create_and_run(config)

    pending = runner.promote_to_live(shadow["id"])

    assert pending["approval_required"] is True
    assert not (config.workspace / "test-shadow.txt").exists()

    promoted = runner.promote_to_live(shadow["id"], approved_by="test-user")
    live_run_id = promoted["live_run"]["id"]

    assert (config.workspace / "test-shadow.txt").read_text(encoding="utf-8") == "OK\n"
    live = DurableRuntime(config).get_run(live_run_id)
    assert live.status == "succeeded"
    assert live.metadata["shadow_run_id"] == shadow["id"]
    assert promoted["comparison"]["success_match"] is True
    assert promoted["shadow_run"]["status"] == "promoted"


def test_shadow_endpoints_work(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    created = client.post("/api/shadow", json={"objective": "crée un fichier api-shadow.txt avec API"})
    assert created.status_code == 200
    shadow_id = created.json()["id"]
    assert client.get("/api/shadow").status_code == 200
    completed = client.post(f"/api/shadow/{shadow_id}/run", json={})
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"
    assert client.get(f"/api/shadow/{shadow_id}").status_code == 200
    assert client.get(f"/api/shadow/{shadow_id}/diff").json()["created"][0]["path"] == "api-shadow.txt"
    assert client.get(f"/api/shadow/{shadow_id}/risk").json()["recommendation"] == "require_approval"
    pending = client.post(f"/api/shadow/{shadow_id}/promote", json={})
    assert pending.status_code == 200
    assert pending.json()["approval_required"] is True
    promoted = client.post(f"/api/shadow/{shadow_id}/promote", json={"approved_by": "api-user"})
    assert promoted.status_code == 200
    assert client.get(f"/api/shadow/{shadow_id}/comparison").status_code == 200


def test_workflow_can_run_in_shadow_and_destructive_live_requires_shadow(tmp_path: Path):
    config = cfg(tmp_path)
    (config.workspace / "workflow-delete.txt").write_text("keep", encoding="utf-8")
    runner = WorkflowRunner(config)
    workflow = runner.create_workflow(
        {
            "name": "Delete in shadow",
            "steps": [
                {
                    "id": "delete",
                    "type": "tool",
                    "name": "Delete",
                    "tool": "delete_file",
                    "arguments": {"relative_path": "workflow-delete.txt"},
                }
            ],
        }
    )

    recommendation = runner.shadow_recommendation(workflow.id)
    assert recommendation["required"] is True
    try:
        runner.run_workflow(workflow.id)
        raise AssertionError("destructive workflow should require shadow")
    except ValueError as exc:
        assert "Shadow run requis" in str(exc)

    client = TestClient(create_app(config))
    result = client.post(f"/api/workflows/{workflow.id}/shadow", json={})
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"
    assert (config.workspace / "workflow-delete.txt").exists()


def test_shadow_cli(tmp_path: Path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    save_config(
        {
            "workspace": {
                "path": str(workspace),
                "full_access": True,
                "shell_full_access": True,
                "allow_delete": True,
            },
            "paths": {
                "db_path": str(tmp_path / "omega.db"),
                "skills_dir": str(tmp_path / "skills"),
                "plugins_dir": str(tmp_path / "plugins"),
            },
            "evals": {"enabled": False},
            "shadow": {"enabled": True},
        },
        config_path,
    )
    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}
    root = Path(__file__).resolve().parents[1]

    created = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "shadow", "create", "crée un fichier cli-shadow.txt avec OK"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    shadow_id = created.stdout.split()[0]
    listed = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "shadow", "list"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    executed = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "shadow", "run", shadow_id],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert shadow_id in listed.stdout
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert not (workspace / "cli-shadow.txt").exists()
