from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.gateway.server import create_app
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.capability_selector import CapabilitySelector
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
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
        db_path=tmp_path / "omega.db",
        connectors_local_http_enabled=False,
        capabilities_max_in_context=4,
    )


def test_connector_migrations_and_builtin_registry(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    config = cfg(tmp_path)
    migrate(config)

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}

    assert {"connectors", "connector_operations", "connector_usage_events", "connector_auth_status"}.issubset(tables)
    items = ConnectorsRegistry(config).list()
    ids = {item.id for item in items}
    assert {"filesystem", "local_http", "github", "mcp_bridge"}.issubset(ids)
    github = next(item for item in items if item.id == "github")
    assert github.enabled is False
    assert github.status == "disabled"
    assert any(item["connector_id"] == "github" and item["status"] == "missing" for item in ConnectorsRegistry(config).auth_status())


def test_openapi_import_creates_disabled_operations(tmp_path: Path):
    config = cfg(tmp_path)
    doc = {
        "openapi": "3.0.0",
        "info": {"title": "Local Notes"},
        "paths": {
            "/notes": {
                "get": {"operationId": "list_notes", "summary": "List notes"},
                "post": {"operationId": "create_note", "summary": "Create note", "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            }
        },
    }

    connector = ConnectorsRegistry(config).import_openapi(document=doc, base_url="http://127.0.0.1:9999")

    assert connector.enabled is False
    assert connector.type == "openapi"
    operations = ConnectorsRegistry(config).operations(connector.id)
    assert {operation.id for operation in operations} == {"list_notes", "create_note"}
    assert next(operation for operation in operations if operation.id == "create_note").requires_approval_default is True


def test_untrusted_disabled_by_default_and_missing_auth_safe(tmp_path: Path):
    config = cfg(tmp_path)
    connector = ConnectorsRegistry(config).create(
        {
            "id": "remote_api",
            "name": "Remote API",
            "type": "custom",
            "enabled": True,
            "trust_level": "untrusted",
            "auth_type": "env_secret",
            "auth_ref": "OMEGA_CONNECTOR_TEST_TOKEN",
            "operations": [{"id": "read", "name": "Read", "action_category": "read_only", "risk_level": "low"}],
        }
    )

    assert connector.enabled is False
    assert connector.status == "disabled"
    assert "OMEGA_CONNECTOR_TEST_TOKEN" in json.dumps(connector.as_api())
    assert "super-secret-value" not in json.dumps(connector.as_api()).lower()


def test_invoke_connector_operation_local_http_journal_and_untrusted_content(tmp_path: Path):
    config = cfg(tmp_path)
    server = _start_server(b'{"ok": true, "token": "token=abc123456789"}')
    try:
        connector = ConnectorsRegistry(config).create(
            {
                "id": "local_mock",
                "name": "Local Mock",
                "type": "local_http",
                "enabled": True,
                "trust_level": "local",
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "operations": [{"id": "hello", "name": "Hello", "method": "GET", "path": "/hello", "action_category": "read_only", "risk_level": "low"}],
            }
        )

        result = ToolBroker(config).call("invoke_connector_operation", {"connector_id": connector.id, "operation_id": "hello", "arguments": {}})

        assert result.status == "completed"
        assert "untrusted_content" in str(result.output)
        assert "token=[REDACTED]" in str(result.output)
        with connect_runtime_db(config) as conn:
            action = conn.execute("SELECT * FROM action_journal WHERE tool_name = 'invoke_connector_operation' ORDER BY created_at DESC LIMIT 1").fetchone()
            usage = conn.execute("SELECT * FROM connector_usage_events WHERE connector_id = 'local_mock' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert action["status"] == "succeeded"
        assert action["action_type"] == "read_only"
        assert usage["status"] == "succeeded"
    finally:
        server.shutdown()


def test_write_operation_requires_approval_and_does_not_execute(tmp_path: Path):
    config = cfg(tmp_path)
    server = _start_server(b'{"created": true}')
    try:
        connector = ConnectorsRegistry(config).create(
            {
                "id": "local_write",
                "name": "Local Write",
                "type": "local_http",
                "enabled": True,
                "trust_level": "local",
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "operations": [
                    {
                        "id": "create",
                        "name": "Create",
                        "method": "POST",
                        "path": "/create",
                        "action_category": "external_side_effect",
                        "risk_level": "high",
                        "requires_approval_default": True,
                    }
                ],
            }
        )

        result = ToolBroker(config).call("invoke_connector_operation", {"connector_id": connector.id, "operation_id": "create", "arguments": {"body": {"x": 1}}})

        assert result.status == "approval_required"
        with connect_runtime_db(config) as conn:
            action = conn.execute("SELECT * FROM action_journal WHERE tool_name = 'invoke_connector_operation' ORDER BY created_at DESC LIMIT 1").fetchone()
        assert action["status"] == "approval_required"
    finally:
        server.shutdown()


def test_connector_capabilities_and_context_selection(tmp_path: Path):
    config = cfg(tmp_path)
    ConnectorsRegistry(config).create(
        {
            "id": "github_local",
            "name": "GitHub Local",
            "type": "custom",
            "enabled": True,
            "trust_level": "local",
            "operations": [{"id": "list_issues", "name": "List issues", "description": "GitHub issues", "action_category": "read_only", "risk_level": "low"}],
        }
    )

    capabilities = CapabilitiesRegistry(config).list()
    assert "connector:github_local:list_issues" in {item.id for item in capabilities}
    selected = CapabilitySelector(config).select_capabilities_for_task("Liste les issues github du repo")
    assert any(item.id == "connector:github_local:list_issues" for item in selected)
    context = build_context(config, None, query="Liste les issues github du repo")
    assert len(context["capabilities"]) <= config.capabilities_max_in_context
    assert any(item["id"] == "connector:github_local:list_issues" for item in context["capabilities"])


def test_connector_endpoints(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))

    response = client.get("/api/connectors")
    assert response.status_code == 200
    assert any(item["id"] == "filesystem" for item in response.json())

    created = client.post(
        "/api/connectors",
        json={
            "id": "api_local",
            "name": "API Local",
            "type": "local_http",
            "enabled": False,
            "trust_level": "local",
            "base_url": "http://127.0.0.1:1",
            "operations": [{"id": "ping", "name": "Ping", "method": "GET", "path": "/ping"}],
        },
    )
    assert created.status_code == 200
    assert created.json()["enabled"] is False
    assert client.get("/api/connectors/api_local/operations").status_code == 200
    assert client.post("/api/connectors/api_local/enable").status_code == 200
    assert client.get("/api/connectors/auth-status").status_code == 200

    imported = client.post(
        "/api/connectors/openapi/import",
        json={"document": {"openapi": "3.0.0", "info": {"title": "Inline API"}, "paths": {"/ping": {"get": {"operationId": "ping"}}}}},
    )
    assert imported.status_code == 200
    assert imported.json()["enabled"] is False


def test_connectors_cli_list_and_auth_status(tmp_path: Path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    save_config(
        {
            "workspace": {"path": str(workspace), "full_access": True, "require_approval": False},
            "paths": {"db_path": str(tmp_path / "omega.db"), "skills_dir": str(tmp_path / "skills"), "plugins_dir": str(tmp_path / "plugins")},
        },
        config_path,
    )
    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}
    root = Path(__file__).resolve().parents[1]

    listed = subprocess.run([sys.executable, "-m", "omega_agent.main", "connectors", "list"], cwd=root, env=env, text=True, capture_output=True, timeout=60)
    auth = subprocess.run([sys.executable, "-m", "omega_agent.main", "connectors", "auth-status"], cwd=root, env=env, text=True, capture_output=True, timeout=60)

    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "filesystem" in listed.stdout
    assert auth.returncode == 0, auth.stdout + auth.stderr
    assert "GITHUB_TOKEN" in auth.stdout


def _start_server(body: bytes) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
