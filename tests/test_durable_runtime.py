from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.storage.migrations import migrate


def cfg(tmp_path: Path, workspace: Path | None = None) -> OmegaConfig:
    root = workspace or tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=root,
        require_approval=True,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        allow_git_write_in_workspace=True,
        db_path=tmp_path / "omega.db",
    )


def test_runtime_migrations_are_idempotent_and_create_tables(tmp_path: Path):
    config = cfg(tmp_path)
    migrate(config)
    with connect_runtime_db(config) as conn:
        conn.execute("INSERT INTO sessions(id, title, created_at, updated_at) VALUES ('existing', 'Existing', 't', 't')")
    migrate(config)
    migrate(config)

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        session = conn.execute("SELECT title FROM sessions WHERE id = 'existing'").fetchone()

    assert {"runs", "run_steps", "checkpoints", "action_journal", "file_snapshots", "rollback_events", "dead_letter_runs"}.issubset(tables)
    assert session["title"] == "Existing"


def test_durable_runtime_lifecycle_and_checkpoint(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Runtime")
    runtime = DurableRuntime(config)

    run = runtime.create_run(session.id, "Faire quelque chose")
    assert run.status == "pending"
    assert runtime.list_checkpoints(run.id)
    assert runtime.start_run(run.id).status == "running"
    step = runtime.append_step(run.id, "reasoning", "Analyse", input={"x": 1}, status="running")
    assert runtime.complete_step(step.id, {"ok": True}).status == "succeeded"
    assert runtime.pause_run(run.id).status == "paused"
    assert runtime.resume_run(run.id).status == "running"
    assert runtime.complete_run(run.id, "ok").status == "succeeded"

    failed = runtime.create_run(session.id, "Erreur")
    runtime.start_run(failed.id)
    assert runtime.fail_run(failed.id, "command not found").status == "failed"


def test_write_existing_file_creates_snapshot_and_rollback_restores(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Snapshot")
    target = config.workspace / "existing.txt"
    target.write_text("OLD", encoding="utf-8")

    result = ToolBroker(config).call("write_file", {"relative_path": "existing.txt", "content": "NEW"}, session_id=session.id)

    assert result.status == "completed"
    assert target.read_text(encoding="utf-8") == "NEW"
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    snapshots = DurableRuntime(config).list_snapshots(run_id=run.id)
    assert snapshots[0].existed_before is True

    rollback = DurableRuntime(config).rollback_snapshot(snapshots[0].id)

    assert rollback["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "OLD"


def test_create_file_snapshot_rolls_back_by_deleting_created_file(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Create")
    broker = ToolBroker(config)

    result = broker.call("write_file", {"relative_path": "new.txt", "content": "OK"}, session_id=session.id)

    assert result.status == "completed"
    assert (config.workspace / "new.txt").exists()
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    snapshot = DurableRuntime(config).list_snapshots(run_id=run.id)[0]
    assert snapshot.existed_before is False

    DurableRuntime(config).rollback_snapshot(snapshot.id)

    assert not (config.workspace / "new.txt").exists()


def test_delete_file_snapshot_rolls_back_by_restoring(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Delete")
    target = config.workspace / "delete-me.txt"
    target.write_text("SAVE", encoding="utf-8")

    result = ToolBroker(config).call("delete_file", {"relative_path": "delete-me.txt"}, session_id=session.id)

    assert result.status == "completed"
    assert not target.exists()
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    snapshot = DurableRuntime(config).list_snapshots(run_id=run.id)[0]

    DurableRuntime(config).rollback_snapshot(snapshot.id)

    assert target.read_text(encoding="utf-8") == "SAVE"


def test_delete_file_workspace_snapshot_created(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Delete snapshot")
    target = config.workspace / "delete-snapshot.txt"
    target.write_text("SAVE", encoding="utf-8")

    result = ToolBroker(config).call(
        "delete_file",
        {"relative_path": "delete-snapshot.txt"},
        session_id=session.id,
    )

    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    snapshots = DurableRuntime(config).list_snapshots(run_id=run.id)
    actions = DurableRuntime(config).list_actions(run.id)

    assert result.status == "completed"
    assert len(snapshots) == 1
    assert snapshots[0].existed_before is True
    assert actions[0].action_type == "destructive_write"
    assert actions[0].snapshot_id == snapshots[0].id
    assert actions[0].rollback_available is True


def test_outside_workspace_is_denied_and_journaled(tmp_path: Path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.txt"
    config = cfg(tmp_path, workspace=workspace)
    session = SessionsStore(config).create_session("Denied")

    result = ToolBroker(config).call("write_file", {"relative_path": str(outside), "content": "x"}, session_id=session.id)

    assert result.status == "denied"
    assert not outside.exists()
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    actions = DurableRuntime(config).list_actions(run.id)
    assert actions[0].status == "denied"


def test_snapshot_outside_workspace_is_refused(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Snapshot denied")
    runtime = DurableRuntime(config)
    run = runtime.create_run(session.id, "snapshot")

    with pytest.raises(PermissionError):
        runtime.create_snapshot_for_paths(run.id, None, [str(tmp_path / "outside.txt")])


def test_gateway_chat_creates_run_action_and_file(tmp_path: Path):
    config = cfg(tmp_path)
    app = create_app(config)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "Crée acceptance-runtime.txt dans mon workspace avec le texte OK"})

    assert response.status_code == 200
    assert (config.workspace / "acceptance-runtime.txt").read_text(encoding="utf-8") == "OK"
    run_id = response.json()["run_id"]
    assert run_id
    assert client.get("/api/runs").json()
    assert client.get(f"/api/runs/{run_id}/steps").json()
    assert client.get(f"/api/runs/{run_id}/actions").json()[0]["tool_name"] == "write_file"
    assert client.get(f"/api/runs/{run_id}/snapshots").json()
