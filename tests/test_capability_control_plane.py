import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.gateway.server import create_app
from omega_agent.runtime.a2a_agents import A2AAgentsRegistry
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.capability_selector import CapabilitySelector
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.mcp_servers import MCPServersRegistry
from omega_agent.runtime.storage import connect_runtime_db


def cfg(tmp_path: Path, *, max_capabilities: int = 20) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    skills_dir = tmp_path / "skills"
    plugins_dir = tmp_path / "plugins"
    workspace.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=True,
        workspace_full_access=True,
        db_path=tmp_path / "omega.db",
        skills_dir=skills_dir,
        plugins_dir=plugins_dir,
        capabilities_max_in_context=max_capabilities,
    )


def seed_skill_and_plugin(config: OmegaConfig) -> None:
    skill_dir = config.skills_dir / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "metadata.json").write_text(
        json.dumps({"id": "local-skill", "name": "Local Skill", "description": "Skill locale", "enabled": True, "risk_level": "low"}),
        encoding="utf-8",
    )
    (skill_dir / "skill.md").write_text("# Local Skill\n", encoding="utf-8")

    plugin_dir = config.plugins_dir / "untrusted-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "id": "untrusted-plugin",
                "name": "Untrusted Plugin",
                "version": "0.1.0",
                "description": "Plugin manifest only",
                "enabled": True,
                "trust_level": "untrusted",
                "permissions": [],
                "declares": {"tools": [], "skills": [], "channels": [], "hooks": []},
            }
        ),
        encoding="utf-8",
    )


def test_capabilities_registry_aggregates_sources_and_disables_untrusted(tmp_path: Path):
    config = cfg(tmp_path)
    seed_skill_and_plugin(config)

    items = CapabilitiesRegistry(config).list()
    ids = {item.id for item in items}

    assert "tool:write_file" in ids
    assert "skill:local-skill" in ids
    assert "plugin:untrusted-plugin" in ids
    assert "provider:codex" in ids
    assert "channel:web" in ids
    plugin = next(item for item in items if item.id == "plugin:untrusted-plugin")
    assert plugin.enabled is False
    assert plugin.owner == "untrusted"


def test_capability_selector_filters_disabled_auth_missing_and_respects_limit(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = cfg(tmp_path, max_capabilities=3)
    registry = CapabilitiesRegistry(config)
    registry.disable("tool:write_file")

    selected = CapabilitySelector(config).select_capabilities_for_task("Crée un fichier test.txt dans le workspace")

    assert len(selected) <= 3
    assert all(item.enabled for item in selected)
    assert all(not (item.requires_auth and item.auth_status != "configured") for item in selected)
    assert "tool:write_file" not in {item.id for item in selected}


def test_mcp_and_a2a_manifests_are_visible_but_not_available_and_redacted(tmp_path: Path):
    config = cfg(tmp_path)
    mcp = MCPServersRegistry(config).add(name="Remote MCP", url="https://example.test/mcp?token=secretsecret")
    a2a = A2AAgentsRegistry(config).add(name="Remote Agent", endpoint="https://agents.test/a2a")

    items = CapabilitiesRegistry(config).list()
    mcp_cap = next(item for item in items if item.id == f"mcp_server:{mcp.id}")
    a2a_cap = next(item for item in items if item.id == f"a2a_agent:{a2a.id}")

    assert mcp.enabled is False
    assert a2a.enabled is False
    assert mcp_cap.available is False
    assert a2a_cap.available is False
    assert "[REDACTED]" in json.dumps(mcp.as_api())


def test_context_builder_injects_selected_capabilities_not_everything(tmp_path: Path):
    config = cfg(tmp_path, max_capabilities=2)

    context = build_context(config, None, query="Liste les fichiers du workspace")
    total = len(CapabilitiesRegistry(config).list())

    assert 0 < len(context["capabilities"]) <= 2
    assert len(context["capabilities"]) < total
    assert "Capabilities selectionnees" in context["system_prompt"]


def test_capability_api_endpoints_and_usage(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert any(item["id"] == "tool:write_file" for item in response.json())

    refresh = client.post("/api/capabilities/refresh")
    assert refresh.status_code == 200

    mcp_response = client.post("/api/mcp/servers", json={"name": "API MCP", "url": "https://example.test/mcp"})
    assert mcp_response.status_code == 200
    assert mcp_response.json()["enabled"] is False

    a2a_response = client.post("/api/a2a/agents", json={"name": "API Agent", "endpoint": "https://example.test/a2a"})
    assert a2a_response.status_code == 200
    assert a2a_response.json()["enabled"] is False

    usage = client.get("/api/capabilities/usage")
    assert usage.status_code == 200


def test_capabilities_cli_list(tmp_path: Path):
    config_path = tmp_path / "config.json"
    save_config(
        {
            "workspace": {"path": str(tmp_path / "workspace"), "full_access": True},
            "paths": {"db_path": str(tmp_path / "omega.db"), "skills_dir": str(tmp_path / "skills"), "plugins_dir": str(tmp_path / "plugins")},
        },
        config_path,
    )
    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}

    result = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "capabilities", "list"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert result.returncode == 0
    assert "tool:write_file" in result.stdout
