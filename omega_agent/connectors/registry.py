from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.connectors.base import Connector, ConnectorOperation, normalize_action_category, normalize_risk
from omega_agent.connectors.connector_auth import auth_status_record, compute_auth_status
from omega_agent.connectors.connector_usage import ConnectorUsageStore
from omega_agent.connectors.filesystem import filesystem_operations
from omega_agent.connectors.github import github_operations
from omega_agent.connectors.local_http import invoke_local_http, validate_local_base_url
from omega_agent.connectors.mcp_bridge import mcp_bridge_operations
from omega_agent.connectors.openapi import load_openapi_document, operations_from_openapi
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.mcp_servers import MCPServersRegistry
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.tools.files import _delete_file, _list_files, _read_file, _write_file


class ConnectorsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self.usage = ConnectorUsageStore(config)

    def list(self, *, refresh: bool = True, type: str | None = None, enabled: bool | None = None, query: str | None = None) -> list[Connector]:
        if refresh and self.config.connectors_enabled:
            self.refresh_builtins()
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM connectors ORDER BY name COLLATE NOCASE ASC").fetchall()
        connectors = [self._connector_from_row(row) for row in rows]
        if type:
            connectors = [item for item in connectors if item.type == type]
        if enabled is not None:
            connectors = [item for item in connectors if item.enabled is enabled]
        if query:
            needle = query.strip().lower()
            connectors = [
                item
                for item in connectors
                if needle in item.id.lower()
                or needle in item.name.lower()
                or needle in item.description.lower()
                or any(needle in scope.lower() for scope in item.scopes)
            ]
        return connectors

    def get(self, connector_id: str, *, refresh: bool = True) -> Connector | None:
        if refresh and self.config.connectors_enabled:
            self.refresh_builtins()
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM connectors WHERE id = ?", (connector_id,)).fetchone()
        return self._connector_from_row(row) if row else None

    def operations(self, connector_id: str) -> list[ConnectorOperation]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM connector_operations WHERE connector_id = ? ORDER BY name COLLATE NOCASE ASC", (connector_id,)).fetchall()
        return [_operation_from_row(row) for row in rows]

    def get_operation(self, connector_id: str, operation_id: str) -> ConnectorOperation | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT * FROM connector_operations WHERE connector_id = ? AND id = ?",
                (connector_id, operation_id),
            ).fetchone()
        return _operation_from_row(row) if row else None

    def create(self, values: dict[str, Any]) -> Connector:
        now = _now()
        connector_id = _slug(str(values.get("id") or values.get("name") or uuid4().hex))
        trust_level = _trust(values.get("trust_level") or "untrusted")
        enabled = bool(values.get("enabled", False))
        if trust_level in {"untrusted", "blocked"} and self.config.connectors_untrusted_disabled_by_default:
            enabled = False
        connector = Connector(
            id=connector_id,
            type=_connector_type(values.get("type") or "custom"),
            name=str(values.get("name") or connector_id),
            description=str(values.get("description") or ""),
            enabled=enabled,
            trust_level=trust_level,
            auth_type=_auth_type(values.get("auth_type") or "none"),
            auth_ref=_optional_str(values.get("auth_ref")),
            base_url=_optional_str(values.get("base_url")),
            scopes=_list(values.get("scopes")),
            operations=[],
            risk_level=normalize_risk(str(values.get("risk_level") or "medium")),
            status="unknown",
            created_at=now,
            updated_at=now,
            metadata=redact(dict(values.get("metadata") or values.get("metadata_json") or {})),
        )
        connector = replace(connector, status=self._status_for(connector))
        operations = [
            _operation_from_payload(connector.id, item)
            for item in _list(values.get("operations") or values.get("operations_json"))
            if isinstance(item, dict)
        ]
        self._upsert(connector, operations)
        self.events.add("connector.created", {"id": connector.id, "type": connector.type})
        return self.get(connector.id, refresh=False) or connector

    def patch(self, connector_id: str, values: dict[str, Any]) -> Connector | None:
        current = self.get(connector_id)
        if current is None:
            return None
        allowed = {"name", "description", "enabled", "trust_level", "auth_type", "auth_ref", "base_url", "scopes", "risk_level", "status", "metadata"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Champs connecteur non modifiables: {', '.join(sorted(unknown))}")
        connector = Connector(
            id=current.id,
            type=current.type,
            name=str(values.get("name", current.name)),
            description=str(values.get("description", current.description)),
            enabled=bool(values.get("enabled", current.enabled)),
            trust_level=_trust(values.get("trust_level", current.trust_level)),
            auth_type=_auth_type(values.get("auth_type", current.auth_type)),
            auth_ref=_optional_str(values.get("auth_ref", current.auth_ref)),
            base_url=_optional_str(values.get("base_url", current.base_url)),
            scopes=_list(values.get("scopes", current.scopes)),
            operations=current.operations,
            risk_level=normalize_risk(str(values.get("risk_level", current.risk_level))),
            status=str(values.get("status", current.status)),
            created_at=current.created_at,
            updated_at=_now(),
            metadata=redact(dict(values.get("metadata", current.metadata) or {})),
        )
        connector = replace(connector, status=self._status_for(connector))
        self._upsert(connector, current.operations)
        self.events.add("connector.updated", {"id": connector.id})
        return self.get(connector_id, refresh=False)

    def enable(self, connector_id: str) -> Connector | None:
        connector = self.patch(connector_id, {"enabled": True})
        if connector:
            self.events.add("connector.enabled", {"id": connector_id})
        return connector

    def disable(self, connector_id: str) -> Connector | None:
        connector = self.patch(connector_id, {"enabled": False})
        if connector:
            self.events.add("connector.disabled", {"id": connector_id})
        return connector

    def delete(self, connector_id: str) -> bool:
        current = self.get(connector_id)
        if current is None:
            return False
        if current.trust_level == "builtin" or current.type in {"builtin", "filesystem", "github", "mcp"}:
            raise ValueError("Connecteur builtin non supprimable; desactivez-le.")
        with connect_runtime_db(self.config) as conn:
            conn.execute("DELETE FROM connectors WHERE id = ?", (connector_id,))
        self.events.add("connector.deleted", {"id": connector_id})
        return True

    def refresh_builtins(self) -> dict[str, int]:
        now = _now()
        builtins = [
            Connector(
                id="filesystem",
                type="filesystem",
                name="Workspace filesystem",
                description="Expose les operations fichiers existantes dans le workspace Omega.",
                enabled=True,
                trust_level="builtin",
                auth_type="none",
                scopes=["workspace", "filesystem"],
                operations=filesystem_operations("filesystem"),
                risk_level="high",
                status="available",
                created_at=now,
                updated_at=now,
                metadata={"builtin": True},
            ),
            Connector(
                id="local_http",
                type="local_http",
                name="Local HTTP",
                description="Endpoint HTTP local loopback, desactive par defaut.",
                enabled=bool(self.config.connectors_local_http_enabled),
                trust_level="local",
                auth_type="none",
                base_url="http://127.0.0.1",
                scopes=["local_http"],
                operations=[
                    ConnectorOperation(
                        id="request",
                        connector_id="local_http",
                        name="Local request",
                        description="Appel HTTP local generique vers loopback.",
                        method="GET",
                        path="/",
                        input_schema={"type": "object", "properties": {"query": {"type": "object"}, "body": {"type": "object"}}},
                        risk_level="medium",
                        action_category="read_only",
                    )
                ],
                risk_level="medium",
                status="disabled" if not self.config.connectors_local_http_enabled else "available",
                created_at=now,
                updated_at=now,
                metadata={"builtin": True},
            ),
            Connector(
                id="github",
                type="github",
                name="GitHub",
                description="Manifest GitHub API-first v1 en lecture seule.",
                enabled=bool(self.config.connectors_github_enabled),
                trust_level="builtin",
                auth_type="env_secret",
                auth_ref="GITHUB_TOKEN",
                scopes=["github", "api"],
                operations=github_operations("github"),
                risk_level="medium",
                status="unknown",
                created_at=now,
                updated_at=now,
                metadata={"builtin": True, "manifest_only": True},
            ),
            Connector(
                id="mcp_bridge",
                type="mcp",
                name="MCP bridge",
                description="Expose les manifests MCP du control plane sans execution v1.",
                enabled=False,
                trust_level="local",
                auth_type="none",
                scopes=["mcp", "manifest"],
                operations=mcp_bridge_operations("mcp_bridge"),
                risk_level="medium",
                status="disabled",
                created_at=now,
                updated_at=now,
                metadata={"builtin": True, "manifest_only": True},
            ),
        ]
        for connector in builtins:
            existing = self.get(connector.id, refresh=False)
            enabled = connector.enabled if existing is None else existing.enabled
            created_at = connector.created_at if existing is None else existing.created_at
            merged = replace(connector, enabled=enabled, created_at=created_at, status=self._status_for(replace(connector, enabled=enabled)))
            self._upsert(merged, connector.operations)
        return {"count": len(builtins)}

    def import_openapi(
        self,
        path: str | Path | None = None,
        *,
        document: dict[str, Any] | str | None = None,
        name: str | None = None,
        base_url: str | None = None,
        trust_level: str = "local",
        source: str | None = None,
    ) -> Connector:
        if not self.config.connectors_openapi_import_enabled:
            raise PermissionError("Import OpenAPI desactive par configuration.")
        doc = load_openapi_document(path, document)
        title = name or (((doc.get("info") or {}) if isinstance(doc.get("info"), dict) else {}).get("title")) or (Path(path).stem if path else "openapi")
        connector_id = _unique_openapi_id(str(title))
        operations = operations_from_openapi(doc, connector_id)
        connector = Connector(
            id=connector_id,
            type="openapi",
            name=str(title),
            description=str(((doc.get("info") or {}) if isinstance(doc.get("info"), dict) else {}).get("description") or "OpenAPI connector"),
            enabled=False,
            trust_level=_trust(trust_level),
            auth_type="none",
            base_url=base_url,
            scopes=["api", "openapi"],
            operations=operations,
            risk_level=_max_risk([operation.risk_level for operation in operations]),
            status="disabled",
            created_at=_now(),
            updated_at=_now(),
            metadata=redact({"source": source or (str(path) if path else "inline"), "openapi": (doc.get("openapi") or doc.get("swagger") or "")}),
        )
        if base_url:
            validate_local_base_url(base_url)
        self._upsert(connector, operations)
        self.events.add("connector.created", {"id": connector.id, "type": "openapi", "operations": len(operations)})
        return self.get(connector.id, refresh=False) or connector

    def auth_status(self) -> list[dict[str, Any]]:
        self.refresh_builtins()
        records = []
        with connect_runtime_db(self.config) as conn:
            for connector in self.list(refresh=False):
                record = auth_status_record(connector)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO connector_auth_status(
                        id, connector_id, status, auth_type, auth_ref, last_checked_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        connector.id,
                        connector.id,
                        record.status,
                        record.auth_type,
                        record.auth_ref,
                        record.last_checked_at,
                        json.dumps(record.metadata, ensure_ascii=False),
                    ),
                )
                records.append(record.as_api())
        return records

    def test_connector(self, connector_id: str) -> dict[str, Any]:
        connector = self.get(connector_id)
        if connector is None:
            raise KeyError(connector_id)
        return {
            "id": connector.id,
            "enabled": connector.enabled,
            "status": connector.status,
            "auth_status": compute_auth_status(connector),
            "operations_count": len(connector.operations),
            "manifest_only": bool(connector.metadata.get("manifest_only")),
        }

    def invoke_operation(self, connector_id: str, operation_id: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        connector = self.get(connector_id)
        operation = self.get_operation(connector_id, operation_id)
        args = dict(arguments or {})
        if connector is None:
            self.usage.record(connector_id, operation_id, status="error", error="connector_not_found")
            raise KeyError(f"Connecteur introuvable: {connector_id}")
        if operation is None:
            self.usage.record(connector_id, operation_id, status="error", error="operation_not_found")
            raise KeyError(f"Operation introuvable: {operation_id}")
        if not connector.enabled:
            self.usage.record(connector_id, operation_id, status="disabled")
            raise PermissionError(f"Connecteur desactive: {connector_id}")
        if not operation.enabled:
            self.usage.record(connector_id, operation_id, status="disabled")
            raise PermissionError(f"Operation desactivee: {operation_id}")
        if compute_auth_status(connector) == "missing":
            self.usage.record(connector_id, operation_id, status="missing_auth")
            raise PermissionError(f"Auth manquante pour {connector_id}: {connector.auth_ref}")
        try:
            result = self._invoke_enabled(connector, operation, args)
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            self.usage.record(connector_id, operation_id, status="error", latency_ms=latency_ms, error=str(exc))
            self.events.add("connector.error", {"connector_id": connector_id, "operation_id": operation_id, "error": str(exc)})
            raise
        latency_ms = int((time.monotonic() - started) * 1000)
        self.usage.record(connector_id, operation_id, status="succeeded", latency_ms=latency_ms, metadata={"untrusted_content": result.get("untrusted_content")})
        self.events.add("connector.used", {"connector_id": connector_id, "operation_id": operation_id, "latency_ms": latency_ms})
        return redact(result)

    def operation_policy_context(self, connector_id: str, operation_id: str) -> dict[str, Any]:
        connector = self.get(connector_id)
        operation = self.get_operation(connector_id, operation_id)
        if connector is None:
            raise KeyError(f"Connecteur introuvable: {connector_id}")
        if operation is None:
            raise KeyError(f"Operation introuvable: {operation_id}")
        return {
            "connector_id": connector.id,
            "operation_id": operation.id,
            "capability_id": f"connector:{connector.id}:{operation.id}",
            "source_trust": connector.trust_level,
            "action_category": operation.action_category,
            "risk_level": operation.risk_level,
            "requires_approval_default": operation.requires_approval_default,
            "resource": connector.base_url or connector.id,
            "connector_enabled": connector.enabled,
            "operation_enabled": operation.enabled,
            "auth_status": compute_auth_status(connector),
        }

    def _invoke_enabled(self, connector: Connector, operation: ConnectorOperation, arguments: dict[str, Any]) -> dict[str, Any]:
        if connector.type == "filesystem":
            return {"connector_id": connector.id, "operation_id": operation.id, "result": self._invoke_filesystem(operation, arguments)}
        if connector.type in {"local_http", "openapi"} and connector.base_url:
            return invoke_local_http(self.config, connector, operation, arguments)
        if connector.type == "mcp" and operation.id == "list_servers":
            return {"connector_id": connector.id, "operation_id": operation.id, "manifest_only": True, "servers": [item.as_api() for item in MCPServersRegistry(self.config).list()]}
        return {
            "connector_id": connector.id,
            "operation_id": operation.id,
            "manifest_only": True,
            "untrusted_content": connector.trust_level not in {"builtin", "local"},
            "message": "Execution externe non implementee en v1.",
        }

    def _invoke_filesystem(self, operation: ConnectorOperation, arguments: dict[str, Any]) -> str:
        if operation.id == "list_files":
            return _list_files(self.config, str(arguments.get("relative_path", ".")))
        if operation.id == "read_file":
            return _read_file(self.config, str(arguments.get("relative_path", "")))
        if operation.id == "write_file":
            return _write_file(self.config, str(arguments.get("relative_path", "")), str(arguments.get("content", "")))
        if operation.id == "delete_file":
            return _delete_file(self.config, str(arguments.get("relative_path", "")))
        raise KeyError(operation.id)

    def _status_for(self, connector: Connector) -> str:
        if not connector.enabled:
            return "disabled"
        if connector.trust_level == "blocked":
            return "disabled"
        auth = compute_auth_status(connector)
        if auth == "missing":
            return "missing_auth"
        if connector.type == "local_http" and connector.base_url:
            try:
                validate_local_base_url(connector.base_url)
            except Exception:
                return "error"
        return "available"

    def _upsert(self, connector: Connector, operations: list[ConnectorOperation]) -> None:
        connector = replace(connector, operations=operations, status=self._status_for(connector), updated_at=connector.updated_at or _now())
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO connectors(
                    id, type, name, description, enabled, trust_level, auth_type, auth_ref,
                    base_url, scopes_json, operations_json, risk_level, status,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connector.id,
                    connector.type,
                    connector.name,
                    connector.description,
                    1 if connector.enabled else 0,
                    connector.trust_level,
                    connector.auth_type,
                    connector.auth_ref,
                    connector.base_url,
                    json.dumps(connector.scopes, ensure_ascii=False),
                    json.dumps([operation.as_api() for operation in operations], ensure_ascii=False),
                    connector.risk_level,
                    connector.status,
                    connector.created_at or _now(),
                    connector.updated_at or _now(),
                    json.dumps(redact(connector.metadata), ensure_ascii=False),
                ),
            )
            conn.execute("DELETE FROM connector_operations WHERE connector_id = ?", (connector.id,))
            for operation in operations:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO connector_operations(
                        id, connector_id, name, description, method, path,
                        input_schema_json, output_schema_json, risk_level,
                        requires_approval_default, action_category, enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation.id,
                        connector.id,
                        operation.name,
                        operation.description,
                        operation.method,
                        operation.path,
                        json.dumps(operation.input_schema or {}, ensure_ascii=False),
                        json.dumps(operation.output_schema or {}, ensure_ascii=False),
                        normalize_risk(operation.risk_level),
                        1 if operation.requires_approval_default else 0,
                        normalize_action_category(operation.action_category),
                        1 if operation.enabled else 0,
                    ),
                )
            auth_record = auth_status_record(connector)
            conn.execute(
                """
                INSERT OR REPLACE INTO connector_auth_status(
                    id, connector_id, status, auth_type, auth_ref, last_checked_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    connector.id,
                    connector.id,
                    auth_record.status,
                    auth_record.auth_type,
                    auth_record.auth_ref,
                    auth_record.last_checked_at,
                    json.dumps(auth_record.metadata, ensure_ascii=False),
                ),
            )

    def _connector_from_row(self, row) -> Connector:
        operations = self.operations(row["id"])
        return Connector(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            description=row["description"] or "",
            enabled=bool(row["enabled"]),
            trust_level=row["trust_level"],
            auth_type=row["auth_type"],
            auth_ref=row["auth_ref"],
            base_url=row["base_url"],
            scopes=_json_list(row["scopes_json"]),
            operations=operations,
            risk_level=row["risk_level"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_json_dict(row["metadata_json"]),
        )


def _operation_from_row(row) -> ConnectorOperation:
    return ConnectorOperation(
        id=row["id"],
        connector_id=row["connector_id"],
        name=row["name"],
        description=row["description"] or "",
        method=row["method"],
        path=row["path"],
        input_schema=_json_dict(row["input_schema_json"]),
        output_schema=_json_dict(row["output_schema_json"]),
        risk_level=normalize_risk(row["risk_level"]),
        requires_approval_default=bool(row["requires_approval_default"]),
        action_category=normalize_action_category(row["action_category"]),
        enabled=bool(row["enabled"]),
    )


def _operation_from_payload(connector_id: str, payload: dict[str, Any]) -> ConnectorOperation:
    return ConnectorOperation(
        id=_slug(str(payload.get("id") or payload.get("name") or uuid4().hex)),
        connector_id=connector_id,
        name=str(payload.get("name") or payload.get("id") or "Operation"),
        description=str(payload.get("description") or ""),
        method=_optional_str(payload.get("method")),
        path=_optional_str(payload.get("path")),
        input_schema=payload.get("input_schema") or payload.get("input_schema_json") or {},
        output_schema=payload.get("output_schema") or payload.get("output_schema_json") or {},
        risk_level=normalize_risk(str(payload.get("risk_level") or "medium")),
        requires_approval_default=bool(payload.get("requires_approval_default", False)),
        action_category=normalize_action_category(str(payload.get("action_category") or "read_only")),
        enabled=bool(payload.get("enabled", True)),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    import re

    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9_.:-]+", "_", lowered).strip("_")
    return lowered or uuid4().hex


def _unique_openapi_id(name: str) -> str:
    return f"openapi:{_slug(name)}:{uuid4().hex[:8]}"


def _connector_type(value: str) -> str:
    lowered = str(value or "custom").strip().lower()
    return lowered if lowered in {"builtin", "openapi", "local_http", "mcp", "github", "filesystem", "custom"} else "custom"


def _trust(value: str) -> str:
    lowered = str(value or "untrusted").strip().lower()
    return lowered if lowered in {"builtin", "local", "untrusted", "blocked"} else "untrusted"


def _auth_type(value: str) -> str:
    lowered = str(value or "none").strip().lower()
    return lowered if lowered in {"none", "env_secret", "oauth_stub", "token_stub"} else "none"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else [value]
        except Exception:
            return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return value
    return list(value) if isinstance(value, tuple) else []


def _json_list(value: str | None) -> list[str]:
    loaded = _json(value, [])
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def _json_dict(value: str | None) -> dict[str, Any]:
    loaded = _json(value, {})
    return loaded if isinstance(loaded, dict) else {}


def _json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _max_risk(values: list[str]) -> str:
    ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if not values:
        return "medium"
    return max((normalize_risk(item) for item in values), key=lambda item: ranks[item])
