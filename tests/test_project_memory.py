from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.decision_log import DecisionLog
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.project_memory import ProjectMemoryStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "workspace_full_access": True,
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_migrations_create_project_memory_tables(tmp_path: Path):
    config = cfg(tmp_path)

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        decision_columns = {row["name"] for row in conn.execute("PRAGMA table_info(decisions)").fetchall()}

    assert {"memory_entries", "memory_provenance", "memory_conflicts", "memory_suggestions", "decisions"}.issubset(tables)
    assert {"session_id", "alternatives_json", "status", "created_by", "updated_at", "metadata_json"}.issubset(decision_columns)


def test_create_memory_requires_provenance_and_searches(tmp_path: Path):
    config = cfg(tmp_path)
    store = ProjectMemoryStore(config)

    memory = store.create_memory(
        "project",
        "Use pytest -q for fast validation",
        "procedure",
        {"source_type": "manual", "source_label": "test"},
        tags=["tests"],
        project_id="default",
        key="test-command",
    )

    assert memory.id
    assert store.search_memory("pytest", project_id="default")[0].id == memory.id
    try:
        store.create_memory("project", "No source", "fact", None, project_id="default")
    except ValueError as exc:
        assert "Provenance" in str(exc)
    else:
        raise AssertionError("memory without provenance should be refused")


def test_archived_and_deleted_memories_are_not_injected_and_limit_is_respected(tmp_path: Path):
    config = cfg(tmp_path, memory_max_context_memories=2)
    store = ProjectMemoryStore(config)
    for index in range(4):
        store.create_memory(
            "project",
            f"omega project convention {index}",
            "fact",
            {"source_type": "manual", "source_label": "test"},
            project_id="default",
            key=f"convention-{index}",
        )
    archived = store.create_memory("project", "obsolete convention", "fact", {"source_type": "manual"}, project_id="default", key="obsolete")
    deleted = store.create_memory("project", "deleted convention", "fact", {"source_type": "manual"}, project_id="default", key="deleted")
    store.archive_memory(archived.id)
    store.delete_memory(deleted.id)

    context = build_context(config, None, query="omega project convention")

    assert len(context["memories"]) == 2
    ids = {item["id"] for item in context["memories"]}
    assert archived.id not in ids
    assert deleted.id not in ids


def test_decision_add_list_archive(tmp_path: Path):
    config = cfg(tmp_path)
    log = DecisionLog(config)

    decision = log.add_decision(
        "Use local config",
        "config.json remains the source of truth",
        "Local-first predictable setup",
        project_id="default",
        provenance={"source_type": "manual", "source_label": "test"},
    )

    assert log.list_decisions(project_id="default")[0].id == decision.id
    archived = log.archive_decision(decision.id)
    assert archived is not None
    assert archived.status == "archived"


def test_memory_suggestion_accept_reject(tmp_path: Path):
    config = cfg(tmp_path)
    runtime = DurableRuntime(config)
    session = SessionsStore(config).create_session("Memory suggestions")
    run = runtime.create_run(session.id, "Remember a lesson")
    store = ProjectMemoryStore(config)

    accepted = store.create_suggestion(run.id, "warning", "Do not store secrets", "security", project_id="default")
    rejected = store.create_suggestion(run.id, "fact", "Transient note", "low value", project_id="default")

    memory = store.accept_suggestion(accepted.id)
    assert memory is not None
    assert memory.content == "Do not store secrets"
    assert store.reject_suggestion(rejected.id) is True
    assert store.get_suggestion(rejected.id).status == "rejected"


def test_memory_redacts_secret_values_and_detects_conflict(tmp_path: Path):
    config = cfg(tmp_path)
    store = ProjectMemoryStore(config)

    redacted = store.create_memory(
        "project",
        "Provider key is sk-secretsecretsecret",
        "fact",
        {"source_type": "manual"},
        project_id="default",
        key="provider-key",
    )
    first = store.create_memory("project", "Use black formatting", "preference", {"source_type": "manual"}, project_id="default", key="formatting")
    second = store.create_memory("project", "Use ruff formatting", "preference", {"source_type": "manual"}, project_id="default", key="formatting")

    assert "sk-secret" not in redacted.content
    assert "[REDACTED]" in redacted.content
    conflicts = store.list_conflicts(project_id="default")
    assert any(conflict.memory_b_id == second.id and conflict.memory_a_id == first.id for conflict in conflicts)


def test_memory_endpoints_work(tmp_path: Path):
    config = cfg(tmp_path)
    app = create_app(config)
    client = TestClient(app)

    created = client.post(
        "/api/memory",
        json={"scope": "project", "project_id": "default", "type": "decision", "key": "runtime", "content": "Durable runtime uses checkpoints"},
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    assert client.get("/api/memory/search?q=checkpoints").json()[0]["id"] == memory_id
    patched = client.patch(f"/api/memory/{memory_id}", json={"content": "Durable runtime uses checkpoints and snapshots"})
    assert patched.status_code == 200
    assert "snapshots" in patched.json()["content"]
    assert client.delete(f"/api/memory/{memory_id}").json()["ok"] is True


def test_decision_endpoints_work(tmp_path: Path):
    config = cfg(tmp_path)
    app = create_app(config)
    client = TestClient(app)

    created = client.post("/api/decisions", json={"title": "Keep local-first", "content": "Use local SQLite", "reason": "privacy"})
    assert created.status_code == 200
    decision_id = created.json()["id"]
    assert client.get("/api/decisions").json()[0]["id"] == decision_id
    assert client.delete(f"/api/decisions/{decision_id}").json()["ok"] is True


def test_successful_run_creates_conservative_memory_suggestion(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "Decision: garder config.json comme source principale.")
    runtime = OmegaRuntime(config)
    session = runtime.sessions.create_session("Memory capture")

    output = run_async(runtime.send_message("Decision projet: garder config.json", session_id=session.id))
    suggestions = ProjectMemoryStore(config).list_suggestions()

    assert "config.json" in output
    assert suggestions
    assert suggestions[0].run_id == runtime.last_run_id


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
