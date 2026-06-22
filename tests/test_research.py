from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.research.citation_checker import CitationChecker
from omega_agent.research.evidence_graph import ResearchRepository
from omega_agent.research.research_agent import OmegaResearchAgent
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.storage.migrations import migrate


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "db_path": tmp_path / "omega.db",
        "evals_enabled": False,
        "connectors_enabled": False,
        "research_enabled": True,
        "research_max_sources": 20,
        "research_max_claims": 50,
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_research_migrations_create_evidence_tables(tmp_path: Path):
    config = cfg(tmp_path)
    migrate(config)

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}

    assert {
        "research_runs",
        "research_sources",
        "research_claims",
        "research_evidence",
        "research_reports",
    }.issubset(tables)


def test_research_run_collects_local_file_links_evidence_and_builds_report(tmp_path: Path):
    config = cfg(tmp_path)
    (config.workspace / ".env").write_text("OPENAI_API_KEY=sk-should-never-appear-123456789", encoding="utf-8")
    (config.workspace / "facts.md").write_text(
        "# Omega Research\nOmega Research stores claims and evidence in SQLite.\n"
        "Every factual claim requires a source citation.\n",
        encoding="utf-8",
    )

    run = OmegaResearchAgent(config).start("How does Omega Research store claims and evidence?")
    detail = OmegaResearchAgent(config).detail(run.id)

    assert run.status == "succeeded"
    assert run.report_markdown
    assert "## Limites" in run.report_markdown
    assert "facts.md" in run.report_markdown
    assert detail["sources"][0]["source_type"] == "file"
    assert detail["claims"]
    assert all(item["status"] in {"supported", "weak", "unsupported", "contradicted"} for item in detail["claims"])
    assert detail["evidence"]
    assert detail["graph"]["nodes"]
    assert detail["graph"]["edges"]
    assert "[S1]" in run.report_markdown
    assert ".env" not in run.report_markdown
    assert "should-never-appear" not in run.report_markdown
    assert "http://" not in run.report_markdown
    assert "https://" not in run.report_markdown


def test_unsupported_claim_is_labeled_unsupported(tmp_path: Path):
    config = cfg(tmp_path)
    repository = ResearchRepository(config)
    run = repository.create_run("Question")
    claim = repository.add_claim(run.id, "This factual statement has no collected evidence.", metadata={"claim_type": "factual"})

    verified = CitationChecker(repository).verify_run(run.id)

    assert verified[0].id == claim.id
    assert verified[0].status == "unsupported"
    assert verified[0].confidence == 0


def test_external_manual_source_is_untrusted(tmp_path: Path):
    config = cfg(tmp_path)

    run = OmegaResearchAgent(config).start(
        "What does the external note claim?",
        manual_sources=[
            {
                "source_type": "web",
                "title": "External note",
                "uri": "https://example.invalid/note",
                "content": "The external note claims that Omega Research verifies citations.",
            }
        ],
    )
    sources = OmegaResearchAgent(config).repository.list_sources(run.id)

    assert any(source.source_type == "web" and source.trust_level == "untrusted" for source in sources)


def test_export_writes_inside_workspace_and_creates_snapshot(tmp_path: Path):
    config = cfg(tmp_path)
    (config.workspace / "facts.txt").write_text("Omega Research exports Markdown reports inside the workspace.", encoding="utf-8")
    agent = OmegaResearchAgent(config)
    run = agent.start("Where are Omega Research reports exported?")

    markdown = agent.export(run.id, "markdown")
    json_export = agent.export(run.id, "json")

    markdown_path = config.workspace / markdown["path"]
    json_path = config.workspace / json_export["path"]
    assert markdown_path.exists()
    assert json_path.exists()
    assert markdown_path.is_relative_to(config.workspace)
    assert json.loads(json_path.read_text(encoding="utf-8"))["run"]["id"] == run.id
    snapshots = DurableRuntime(config).list_snapshots(run_id=run.run_id)
    assert len(snapshots) >= 2
    assert all(Path(item.absolute_path).is_relative_to(config.workspace) for item in snapshots)


def test_export_refuses_path_outside_workspace(tmp_path: Path):
    config = cfg(tmp_path, research_export_dir="../outside")
    (config.workspace / "facts.txt").write_text("A local fact used for the report.", encoding="utf-8")
    agent = OmegaResearchAgent(config)
    run = agent.start("What local fact is available?")

    with pytest.raises(PermissionError):
        agent.export(run.id, "markdown")


def test_research_profile_has_read_only_tools_and_no_shell(tmp_path: Path):
    profile = AgentProfilesStore(cfg(tmp_path)).get("omega-research")

    assert profile is not None
    assert {"read_file", "list_files", "search_memory", "invoke_connector_operation"}.issubset(profile.allowed_tools)
    assert "run_shell" not in profile.allowed_tools
    assert profile.policy["connectors_read_only"] is True


def test_research_profile_denies_non_read_only_connector_operation(tmp_path: Path):
    config = cfg(tmp_path, connectors_enabled=True)
    connector = ConnectorsRegistry(config).create(
        {
            "id": "research_write",
            "name": "Research Write",
            "type": "custom",
            "enabled": True,
            "trust_level": "local",
            "operations": [
                {
                    "id": "create",
                    "name": "Create",
                    "action_category": "external_side_effect",
                    "risk_level": "high",
                    "requires_approval_default": True,
                }
            ],
        }
    )
    session = SessionsStore(config).create_session("Research connector policy")
    SessionsStore(config).set_agent_profile(session.id, "omega-research")

    result = ToolBroker(config).call(
        "invoke_connector_operation",
        {"connector_id": connector.id, "operation_id": "create", "arguments": {"body": {"x": 1}}},
        session_id=session.id,
    )

    assert result.status == "denied"
    assert "read-only" in result.output


def test_research_endpoints_work(tmp_path: Path):
    config = cfg(tmp_path)
    (config.workspace / "facts.md").write_text("Omega Research exposes an evidence graph through the gateway.", encoding="utf-8")
    client = TestClient(create_app(config))

    created = client.post("/api/research", json={"question": "What does Omega Research expose?"})

    assert created.status_code == 200
    research_run_id = created.json()["id"]
    assert client.get("/api/research").status_code == 200
    assert client.get(f"/api/research/{research_run_id}").status_code == 200
    assert client.get(f"/api/research/{research_run_id}/sources").json()
    assert client.get(f"/api/research/{research_run_id}/claims").json()
    assert client.get(f"/api/research/{research_run_id}/evidence").json()
    graph = client.get(f"/api/research/{research_run_id}/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    exported = client.post(f"/api/research/{research_run_id}/export", json={"format": "markdown"})
    assert exported.status_code == 200
    assert (config.workspace / exported.json()["path"]).exists()
