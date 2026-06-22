from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from omega_agent.connectors.base import ConnectorOperation

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def load_openapi_document(path: str | Path | None = None, document: dict[str, Any] | str | None = None) -> dict[str, Any]:
    if document is not None:
        if isinstance(document, str):
            return _loads_document(document)
        if isinstance(document, dict):
            return document
        raise ValueError("Document OpenAPI invalide.")
    if path is None:
        raise ValueError("Chemin OpenAPI requis.")
    target = Path(path).expanduser().resolve()
    raw = target.read_text(encoding="utf-8-sig")
    return _loads_document(raw, suffix=target.suffix.lower())


def operations_from_openapi(document: dict[str, Any], connector_id: str) -> list[ConnectorOperation]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI invalide: champ paths manquant.")
    operations: list[ConnectorOperation] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            lowered = str(method).lower()
            if lowered not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            op_id = str(operation.get("operationId") or _operation_id(lowered, str(path)))
            action_category, risk, approval = _classify_operation(lowered)
            operations.append(
                ConnectorOperation(
                    id=op_id,
                    connector_id=connector_id,
                    name=str(operation.get("summary") or operation.get("operationId") or f"{lowered.upper()} {path}"),
                    description=str(operation.get("description") or operation.get("summary") or ""),
                    method=lowered.upper(),
                    path=str(path),
                    input_schema=_input_schema(operation),
                    output_schema=_output_schema(operation),
                    risk_level=risk,
                    requires_approval_default=approval,
                    action_category=action_category,
                    enabled=True,
                )
            )
    return operations


def _loads_document(raw: str, suffix: str = "") -> dict[str, Any]:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        if suffix not in {".yaml", ".yml", ""}:
            raise
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional PyYAML
            raise ValueError("OpenAPI YAML requiert PyYAML ou un fichier JSON.") from exc
        loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError("OpenAPI doit contenir un objet.")
    return loaded


def _operation_id(method: str, path: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
    return f"{method}_{normalized or 'root'}"


def _classify_operation(method: str) -> tuple[str, str, bool]:
    if method in {"get", "head", "options"}:
        return "read_only", "low", False
    if method == "delete":
        return "destructive_write", "high", True
    if method in {"put", "patch"}:
        return "reversible_write", "high", True
    return "external_side_effect", "medium", True


def _input_schema(operation: dict[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    parameters = operation.get("parameters") or []
    if isinstance(parameters, list):
        props = schema["properties"]
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            name = parameter.get("name")
            if not name:
                continue
            props[str(name)] = parameter.get("schema") or {"type": "string"}
    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        content = request_body.get("content") or {}
        if isinstance(content, dict):
            json_content = content.get("application/json") or next(iter(content.values()), {})
            if isinstance(json_content, dict) and isinstance(json_content.get("schema"), dict):
                schema["properties"]["body"] = json_content["schema"]
    return schema


def _output_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return None
    for status in ("200", "201", "default"):
        response = responses.get(status)
        if not isinstance(response, dict):
            continue
        content = response.get("content") or {}
        if not isinstance(content, dict):
            continue
        json_content = content.get("application/json") or next(iter(content.values()), {})
        if isinstance(json_content, dict) and isinstance(json_content.get("schema"), dict):
            return json_content["schema"]
    return None
