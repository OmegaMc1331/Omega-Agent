from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.connectors.connector_auth import compute_auth_status
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.runtime.project_memory import ProjectMemoryStore
from omega_agent.security.redaction import redact, redact_text
from omega_agent.security.sandbox import is_path_inside_workspace

TEXT_SUFFIXES = {
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv", ".tsv",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sql", ".ini", ".cfg",
}
IGNORED_DIRS = {".git", ".omega", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"}


@dataclass(frozen=True)
class CollectedSource:
    source_type: str
    title: str
    content: str
    uri: str | None = None
    locator: str | None = None
    trust_level: str = "untrusted"
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceCollector:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def collect_from_workspace_files(self, query: str) -> list[CollectedSource]:
        root = self.config.workspace.resolve()
        query_tokens = _tokens(query)
        ranked: list[tuple[int, str, Path, str]] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if any(part in IGNORED_DIRS for part in relative.parts) or _sensitive_file(path):
                continue
            if not is_path_inside_workspace(path, root):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            redacted_content = redact_text(content)[:20000]
            lowered = f"{relative.as_posix()}\n{redacted_content}".lower()
            score = sum(lowered.count(token) for token in query_tokens)
            ranked.append((score, relative.as_posix().lower(), path, redacted_content))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        if query_tokens and any(score > 0 for score, *_ in ranked):
            ranked = [item for item in ranked if item[0] > 0]
        return [
            CollectedSource(
                source_type="file",
                title=path.name,
                content=content,
                locator=path.relative_to(root).as_posix(),
                trust_level="local",
                metadata={"workspace_relative_path": path.relative_to(root).as_posix(), "match_score": score},
            )
            for score, _, path, content in ranked[: self.config.research_max_sources]
        ]

    def collect_from_memory(self, query: str) -> list[CollectedSource]:
        if not self.config.memory_enabled:
            return []
        try:
            memories = ProjectMemoryStore(self.config).search_memory(query)
        except (ValueError, OSError):
            return []
        result: list[CollectedSource] = []
        for memory in memories[: min(10, self.config.research_max_sources)]:
            result.append(
                CollectedSource(
                    source_type="memory",
                    title=memory.key or f"Memory {memory.id[:8]}",
                    content=redact_text(memory.content),
                    locator=f"memory:{memory.id}",
                    trust_level="local",
                    metadata={
                        "memory_id": memory.id,
                        "scope": memory.scope,
                        "confidence": memory.confidence,
                        "provenance": redact(memory.provenance),
                    },
                )
            )
        return result

    def collect_from_connectors(self, query: str) -> list[CollectedSource]:
        if not self.config.connectors_enabled:
            return []
        registry = ConnectorsRegistry(self.config)
        collected: list[CollectedSource] = []
        for connector in registry.list():
            if len(collected) >= min(5, self.config.research_max_sources):
                break
            if connector.id == "filesystem" or not connector.enabled or connector.status != "available":
                continue
            if compute_auth_status(connector) not in {"none", "configured"}:
                continue
            is_web = _is_web_connector(connector)
            if is_web and not self.config.research_web_enabled:
                continue
            for operation in connector.operations:
                if operation.action_category != "read_only" or operation.requires_approval_default or not operation.enabled:
                    continue
                arguments = _query_arguments(operation.input_schema or {}, query)
                if arguments is None:
                    continue
                try:
                    payload = registry.invoke_operation(connector.id, operation.id, arguments)
                except Exception:
                    continue
                if payload.get("manifest_only") or payload.get("message") == "Execution externe non implementee en v1.":
                    continue
                content = json.dumps(redact(payload), ensure_ascii=False, indent=2)[: self.config.connectors_max_response_chars]
                collected.append(
                    CollectedSource(
                        source_type="web" if is_web else "connector",
                        title=f"{connector.name}: {operation.name}",
                        content=content,
                        uri=connector.base_url,
                        locator=f"{connector.id}:{operation.id}",
                        trust_level="untrusted" if self.config.research_external_sources_untrusted else "external",
                        metadata={
                            "connector_id": connector.id,
                            "operation_id": operation.id,
                            "connector_trust_level": connector.trust_level,
                            "external_content": True,
                            "instructions_ignored": True,
                        },
                    )
                )
                break
        return collected

    def collect_from_manual_sources(self, sources: list[dict[str, Any]] | None) -> list[CollectedSource]:
        result: list[CollectedSource] = []
        for index, source in enumerate(sources or []):
            content = redact_text(str(source.get("content") or "")).strip()
            if not content:
                continue
            source_type = str(source.get("source_type") or "manual")
            external = source_type in {"web", "connector"} or bool(source.get("external", False))
            result.append(
                CollectedSource(
                    source_type=source_type if source_type in {"file", "memory", "connector", "web", "manual"} else "manual",
                    title=redact_text(str(source.get("title") or f"Manual source {index + 1}")),
                    content=content[:20000],
                    uri=redact_text(str(source.get("uri"))) if source.get("uri") else None,
                    locator=redact_text(str(source.get("locator"))) if source.get("locator") else f"manual:{index + 1}",
                    trust_level="untrusted" if external and self.config.research_external_sources_untrusted else str(source.get("trust_level") or "local"),
                    metadata={**redact(source.get("metadata") or {}), "manual": True, "instructions_ignored": True},
                )
            )
        return result


def _tokens(value: str) -> set[str]:
    stop = {"avec", "dans", "pour", "quoi", "quel", "quelle", "comment", "what", "which", "from", "that", "this", "the"}
    return {token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", value.lower()) if len(token) > 2 and token not in stop}


def _sensitive_file(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered == ".env" or lowered.startswith(".env."):
        return True
    if lowered in {"id_rsa", "id_ed25519", "login data", "local state", "cookies"}:
        return True
    return path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"} or any(token in lowered for token in ("private_key", "credentials", "secrets"))


def _is_web_connector(connector) -> bool:
    haystack = " ".join([connector.id, connector.type, connector.name, *connector.scopes]).lower()
    return "web" in haystack or "search" in haystack


def _query_arguments(schema: dict[str, Any], query: str) -> dict[str, Any] | None:
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    if not isinstance(properties, dict) or not properties:
        return {}
    arguments: dict[str, Any] = {}
    for name in ("query", "q", "search", "term", "text"):
        if name in properties:
            arguments[name] = query
            return arguments
    if set(properties).issubset({"limit", "page", "offset"}):
        return {}
    return None
