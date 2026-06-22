import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.gateway.server import create_app
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.skills.foundry import SkillFoundry
from omega_agent.skills.skill_promoter import SkillPromoter
from omega_agent.skills.skill_store import SkillStore
from omega_agent.skills.skill_validator import SkillValidator


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    skills_dir = tmp_path / "legacy-skills"
    workspace.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=True,
        workspace_full_access=True,
        db_path=tmp_path / "omega.db",
        skills_dir=skills_dir,
        plugins_dir=tmp_path / "plugins",
        evals_enabled=False,
        memory_enabled=False,
    )


def successful_run(config: OmegaConfig, title: str, tools: list[str], *, failed: bool = False) -> str:
    session = SessionsStore(config).create_session(title)
    runtime = DurableRuntime(config)
    run = runtime.create_run(session.id, title)
    runtime.start_run(run.id)
    for tool in tools:
        action = runtime.record_action(run.id, tool, {"relative_path": "."}, {"action": "allow", "risk_level": "low"})
        runtime.mark_action_running(action.id)
        if failed:
            runtime.mark_action_failed(action.id, "test failure")
            runtime.fail_run(run.id, "final failure")
            return run.id
        runtime.mark_action_completed(action.id, {"ok": True})
    runtime.complete_run(run.id, "done")
    return run.id


def test_detects_candidate_from_two_similar_successful_runs(tmp_path: Path):
    config = cfg(tmp_path)
    run_a = successful_run(config, "Audit workspace one", ["list_files", "read_file"])
    run_b = successful_run(config, "Audit workspace two", ["list_files", "read_file"])

    candidates = SkillFoundry(config).detect_candidates()

    assert len(candidates) == 1
    assert candidates[0].source_run_ids == [run_b, run_a]
    assert candidates[0].status == "pending"
    assert candidates[0].proposed_skill["definition"]["safety_policy"]["policy_bypass"] is False


def test_failed_run_and_unredacted_secret_do_not_create_candidates(tmp_path: Path):
    config = cfg(tmp_path)
    successful_run(config, "Failed audit", ["list_files"], failed=True)
    run_a = successful_run(config, "Secret audit one", ["list_files"])
    successful_run(config, "Secret audit two", ["list_files"])
    with connect_runtime_db(config) as conn:
        conn.execute(
            "UPDATE action_journal SET arguments_json = ? WHERE run_id = ?",
            (json.dumps({"api_key": "sk-secretsecretsecret123"}), run_a),
        )

    candidates = SkillFoundry(config).detect_candidates()

    assert candidates == []


def test_accept_test_activate_disable_and_capabilities(tmp_path: Path):
    config = cfg(tmp_path)
    successful_run(config, "Repo review one", ["list_files", "read_file"])
    successful_run(config, "Repo review two", ["list_files", "read_file"])
    candidate = SkillFoundry(config).detect_candidates()[0]
    promoter = SkillPromoter(config)

    skill = promoter.accept_candidate(candidate.id)
    assert skill.status == "draft"
    assert skill.enabled is False
    assert SkillStore(config).get_candidate(candidate.id).status == "accepted"

    test_run = promoter.test_skill(skill.id)
    assert test_run.status == "passed"
    active = promoter.activate(skill.id)
    assert active.status == "active"
    assert f"skill:{skill.id}" in {item.id for item in CapabilitiesRegistry(config).list()}
    context = build_context(config, None, query=f"skill {skill.name}")
    assert any(item["id"] == skill.id for item in context["skills"])

    promoter.disable(skill.id)
    context = build_context(config, None, query=f"skill {skill.name}")
    assert all(item["id"] != skill.id for item in context["skills"])


def test_activate_refuses_failed_or_missing_tests(tmp_path: Path):
    config = cfg(tmp_path)
    successful_run(config, "Build check one", ["list_files", "read_file"])
    successful_run(config, "Build check two", ["list_files", "read_file"])
    candidate = SkillFoundry(config).detect_candidates()[0]
    skill = SkillPromoter(config).accept_candidate(candidate.id)

    try:
        SkillPromoter(config).activate(skill.id)
    except ValueError as exc:
        assert "test passed" in str(exc)
    else:
        raise AssertionError("Activation should require a passing test.")


def test_skill_endpoints(tmp_path: Path):
    config = cfg(tmp_path)
    successful_run(config, "Endpoint task one", ["list_files", "read_file"])
    successful_run(config, "Endpoint task two", ["list_files", "read_file"])
    client = TestClient(create_app(config))

    detected = client.post("/api/skills/candidates/detect")
    assert detected.status_code == 200
    candidate_id = client.get("/api/skills/candidates").json()[0]["id"]
    accepted = client.post(f"/api/skills/candidates/{candidate_id}/accept")
    assert accepted.status_code == 200
    skill_id = accepted.json()["id"]
    assert client.get(f"/api/skills/{skill_id}").status_code == 200
    patched = client.patch(
        f"/api/skills/{skill_id}",
        json={"description": "Updated reviewed draft", "changelog": "Clarify output"},
    )
    assert patched.status_code == 200
    assert patched.json()["version"] == "0.1.1"
    assert client.post(f"/api/skills/{skill_id}/test").json()["status"] == "passed"
    assert client.post(f"/api/skills/{skill_id}/activate").status_code == 200
    assert client.get(f"/api/skills/{skill_id}/usage").status_code == 200
    assert client.post(f"/api/skills/{skill_id}/disable").status_code == 200


def test_validator_rejects_secrets_absolute_paths_and_dangerous_commands(tmp_path: Path):
    config = cfg(tmp_path)
    definition = {
        "name": "unsafe",
        "description": "unsafe",
        "when_to_use": "always",
        "inputs": [],
        "steps": [{"action": "run_shell", "instruction": "sudo rm -rf /"}],
        "required_capabilities": ["run_shell"],
        "safety_policy": {"workspace_only": True, "policy_bypass": False},
        "validation": {"checks": ["static"]},
        "fallback": "stop",
        "output_format": {"summary": "string"},
        "rollback_notes": "restore",
        "metadata": {"api_key": "sk-secretsecretsecret123", "path": "C:\\Users\\someone\\.ssh\\id_rsa"},
    }

    result = SkillValidator(config).validate(definition, [{"name": "static", "type": "static"}])

    assert result.valid is False
    assert any("secret" in error.lower() for error in result.errors)
    assert any("path" in error.lower() for error in result.errors)
    assert any("dangerous" in error.lower() for error in result.errors)


def test_skills_cli_lists_candidates_and_skills(tmp_path: Path):
    config_file = tmp_path / "config.json"
    save_config(
        {
            "workspace": {"path": str(tmp_path / "workspace"), "full_access": True},
            "paths": {
                "db_path": str(tmp_path / "omega.db"),
                "skills_dir": str(tmp_path / "skills"),
                "plugins_dir": str(tmp_path / "plugins"),
            },
            "evals": {"enabled": False},
        },
        config_file,
    )
    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_file)}
    root = Path(__file__).resolve().parents[1]

    candidates = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "skills", "candidates"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    listing = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "skills", "list"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert candidates.returncode == 0
    assert "Aucune candidate" in candidates.stdout
    assert listing.returncode == 0
