from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app


def _config(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=True,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        allow_git_write_in_workspace=True,
        db_path=tmp_path / "omega.db",
    )


def _post_chat(client: TestClient, message: str) -> dict:
    response = client.post("/api/chat", json={"message": message})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"]
    return payload


def _run_actions(client: TestClient, run_id: str) -> list[dict]:
    response = client.get(f"/api/runs/{run_id}/actions")
    assert response.status_code == 200
    return response.json()


def _run_snapshots(client: TestClient, run_id: str) -> list[dict]:
    response = client.get(f"/api/runs/{run_id}/snapshots")
    assert response.status_code == 200
    return response.json()


def test_api_chat_durable_runtime_write_modify_delete_rollback_and_deny(tmp_path: Path):
    config = _config(tmp_path)
    client = TestClient(create_app(config))
    target = config.workspace / "runtime-acceptance.txt"

    create_payload = _post_chat(client, "Crée runtime-acceptance.txt dans mon workspace avec le texte OK")

    assert target.read_text(encoding="utf-8") == "OK"
    create_run_id = create_payload["run_id"]
    steps = client.get(f"/api/runs/{create_run_id}/steps").json()
    assert any(step["type"] == "tool_call" for step in steps)
    create_actions = _run_actions(client, create_run_id)
    assert any(action["tool_name"] == "write_file" and action["status"] == "succeeded" for action in create_actions)
    create_snapshots = _run_snapshots(client, create_run_id)
    assert any(snapshot["workspace_path"] == "runtime-acceptance.txt" and snapshot["existed_before"] is False for snapshot in create_snapshots)

    modify_payload = _post_chat(client, "Modifie runtime-acceptance.txt avec le texte UPDATED")

    assert target.read_text(encoding="utf-8") == "UPDATED"
    modify_snapshots = _run_snapshots(client, modify_payload["run_id"])
    modify_snapshot = next(
        snapshot
        for snapshot in modify_snapshots
        if snapshot["workspace_path"] == "runtime-acceptance.txt" and snapshot["existed_before"] is True
    )
    rollback_response = client.post(f"/api/snapshots/{modify_snapshot['id']}/rollback")
    assert rollback_response.status_code == 200, rollback_response.text
    assert rollback_response.json()["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "OK"

    delete_payload = _post_chat(client, "Supprime runtime-acceptance.txt")

    assert not target.exists()
    delete_snapshots = _run_snapshots(client, delete_payload["run_id"])
    delete_snapshot = next(
        snapshot
        for snapshot in delete_snapshots
        if snapshot["workspace_path"] == "runtime-acceptance.txt" and snapshot["existed_before"] is True
    )
    rollback_delete = client.post(f"/api/snapshots/{delete_snapshot['id']}/rollback")
    assert rollback_delete.status_code == 200, rollback_delete.text
    assert rollback_delete.json()["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "OK"

    outside = tmp_path / "outside-runtime-acceptance.txt"
    denied_payload = _post_chat(client, f"Crée {outside} avec le texte NOPE")

    assert not outside.exists()
    denied_actions = _run_actions(client, denied_payload["run_id"])
    assert any(action["tool_name"] == "write_file" and action["status"] == "denied" for action in denied_actions)
    assert client.get("/api/approvals").json() == []

    events = client.get("/api/timeline", params={"limit": 500}).json()
    event_types = {event["type"] for event in events}
    assert {"run.created", "action.allowed", "snapshot.created", "rollback.completed"}.issubset(event_types)
