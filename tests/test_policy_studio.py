import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.security.policy_profiles import PolicyProfilesStore, PolicyRulesStore
from omega_agent.security.policy_simulator import PolicySimulator
from omega_agent.storage.migrations import migrate


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=False,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        allow_git_write_in_workspace=True,
        db_path=tmp_path / "omega.db",
    )


def test_policy_migrations_and_builtin_profiles(tmp_path: Path):
    config = cfg(tmp_path)
    migrate(config)
    profiles = PolicyProfilesStore(config).list()

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}

    assert {"policy_profiles", "policy_rules", "policy_simulations"}.issubset(tables)
    assert {"local-safe", "developer-workspace", "mobile-access", "untrusted-channel"}.issubset({profile.id for profile in profiles})


def test_policy_simulator_core_cases(tmp_path: Path):
    config = cfg(tmp_path)
    simulator = PolicySimulator(config)

    write = simulator.simulate_policy({"tool_name": "write_file", "arguments": {"relative_path": "test.txt"}})
    outside = simulator.simulate_policy({"tool_name": "write_file", "arguments": {"relative_path": str(tmp_path / "outside.txt")}})
    bulk_delete = simulator.simulate_policy({"tool_name": "delete_file", "arguments": {"relative_path": "old.txt"}, "file_count": 11})
    mobile_delete = simulator.simulate_policy({"tool_name": "delete_file", "arguments": {"relative_path": "old.txt"}, "channel": "mobile"})
    untrusted_shell = simulator.simulate_policy({"tool_name": "run_shell", "arguments": {"command": "npm run build"}, "source_trust": "untrusted"})
    git_push = simulator.simulate_policy({"tool_name": "run_shell", "arguments": {"command": "git push"}})
    system_sensitive = simulator.simulate_policy({"tool_name": "system_exec", "arguments": {"command": "shutdown"}})

    assert write["final_decision"] == "allow"
    assert outside["final_decision"] == "deny"
    assert bulk_delete["final_decision"] == "require_approval"
    assert mobile_delete["final_decision"] == "require_approval"
    assert untrusted_shell["final_decision"] == "deny"
    assert git_push["final_decision"] == "deny"
    assert system_sensitive["final_decision"] == "deny"


def test_custom_rule_influences_tool_broker_and_action_journal(tmp_path: Path):
    config = cfg(tmp_path)
    profile = PolicyProfilesStore(config).create(name="Test Deny", priority=100, default_action="allow")
    PolicyRulesStore(config).create(
        profile_id=profile.id,
        name="Deny blocked writes",
        effect="deny",
        tool_name="write_file",
        resource_pattern="blocked.txt",
        priority=100,
        reason="blocked by test policy",
    )
    session = SessionsStore(config).create_session("Policy")

    denied = ToolBroker(config).call("write_file", {"relative_path": "blocked.txt", "content": "NO"}, session_id=session.id)
    allowed = ToolBroker(config).call("write_file", {"relative_path": "allowed.txt", "content": "OK"}, session_id=session.id)

    assert denied.status == "denied"
    assert "blocked by test policy" in denied.output
    assert not (config.workspace / "blocked.txt").exists()
    assert allowed.status == "completed"
    assert (config.workspace / "allowed.txt").read_text(encoding="utf-8") == "OK"
    with connect_runtime_db(config) as conn:
        row = conn.execute("SELECT policy_decision_json FROM action_journal WHERE tool_name = 'write_file' AND status = 'denied' ORDER BY created_at DESC LIMIT 1").fetchone()
    decision = json.loads(row["policy_decision_json"])
    assert any(rule["name"] == "Deny blocked writes" for rule in decision["matched_rules"])


def test_policy_endpoints(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    assert client.get("/api/policy/profiles").status_code == 200
    rule = client.post(
        "/api/policy/rules",
        json={"profile_id": "developer-workspace", "name": "Deny tmp", "effect": "deny", "tool_name": "write_file", "resource_pattern": "tmp.txt", "reason": "no tmp"},
    )
    assert rule.status_code == 200
    simulation = client.post("/api/policy/simulate", json={"tool_name": "write_file", "arguments": {"relative_path": "tmp.txt"}})
    assert simulation.status_code == 200
    assert simulation.json()["final_decision"] == "deny"
    assert client.get("/api/policy/effective").status_code == 200
    assert client.get("/api/policy/audit").status_code == 200


def test_policy_cli_simulate_and_doctor(tmp_path: Path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "OMEGA_CONFIG_PATH": str(config_path),
            "OMEGA_DB_PATH": str(tmp_path / "omega.db"),
            "OMEGA_WORKSPACE": str(workspace),
            "OMEGA_WORKSPACE_FULL_ACCESS": "true",
            "OMEGA_REQUIRE_APPROVAL": "false",
            "OMEGA_SHELL_FULL_ACCESS_IN_WORKSPACE": "true",
            "OMEGA_ALLOW_DELETE_IN_WORKSPACE": "true",
            "OMEGA_DEFAULT_MODEL": "test",
        }
    )
    root = Path(__file__).resolve().parents[1]
    simulate = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "policy", "simulate", "--tool", "write_file", "--path", "test.txt"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    doctor = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "policy", "doctor"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert simulate.returncode == 0, simulate.stdout + simulate.stderr
    assert '"final_decision": "allow"' in simulate.stdout
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
