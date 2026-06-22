from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.connectors.base import Connector, ConnectorOperation
from omega_agent.security.redaction import redact

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def validate_local_base_url(base_url: str | None) -> str:
    if not base_url:
        raise ValueError("base_url requis pour local_http/openapi execution.")
    parsed = urllib.parse.urlparse(str(base_url))
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Seules les URL HTTP(S) locales sont autorisees.")
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise PermissionError("Connecteur local_http limite a 127.0.0.1, localhost ou ::1.")
    return str(base_url).rstrip("/")


def invoke_local_http(config: OmegaConfig, connector: Connector, operation: ConnectorOperation, arguments: dict[str, Any]) -> dict[str, Any]:
    base_url = validate_local_base_url(connector.base_url)
    method = (operation.method or "GET").upper()
    path = operation.path or "/"
    url = _join_url(base_url, path)
    query = arguments.get("query")
    body = arguments.get("body")
    headers = {"Accept": "application/json, text/plain;q=0.9, */*;q=0.8"}
    if connector.auth_ref:
        secret = os.getenv(connector.auth_ref, "")
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
    if isinstance(query, dict) and query:
        separator = "&" if urllib.parse.urlparse(url).query else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(query, doseq=True)}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    timeout = max(1, int(config.connectors_timeout_seconds or 30))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max(1, int(config.connectors_max_response_chars or 20000)) + 1)
            status_code = int(response.status)
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read(max(1, int(config.connectors_max_response_chars or 20000)) + 1)
        status_code = int(exc.code)
        response_headers = dict(exc.headers.items()) if exc.headers else {}
    text = raw.decode("utf-8", errors="replace")
    max_chars = max(1, int(config.connectors_max_response_chars or 20000))
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return redact(
        {
            "untrusted_content": True,
            "connector_id": connector.id,
            "operation_id": operation.id,
            "status_code": status_code,
            "headers": _safe_headers(response_headers),
            "body": text,
            "truncated": truncated,
        }
    )


def _join_url(base_url: str, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return urllib.parse.urljoin(base_url + "/", path.lstrip("/"))


def _safe_headers(headers: dict[str, Any]) -> dict[str, Any]:
    allowed = {"content-type", "content-length", "date", "server"}
    return {key: value for key, value in headers.items() if key.lower() in allowed}
