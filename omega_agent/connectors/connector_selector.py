from __future__ import annotations

import re

from omega_agent.config import OmegaConfig
from omega_agent.connectors.connector_auth import compute_auth_status
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.security.redaction import redact


class ConnectorSelector:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.registry = ConnectorsRegistry(config)

    def select_connector_for_task(self, message: str, capabilities: list | None = None, project: object | None = None) -> list[dict]:
        limit = max(1, int(getattr(self.config, "capabilities_max_in_context", 20) or 20))
        candidates: list[tuple[int, str, dict]] = []
        for connector in self.registry.list():
            if not connector.enabled or connector.trust_level in {"untrusted", "blocked"}:
                continue
            auth_status = compute_auth_status(connector)
            if auth_status not in {"none", "configured"}:
                continue
            for operation in connector.operations:
                if not operation.enabled:
                    continue
                score = _score(message, connector.name, connector.description, operation.name, operation.description, " ".join(connector.scopes))
                if score <= 0 and connector.id not in {"filesystem"}:
                    continue
                candidates.append(
                    (
                        score,
                        f"{connector.name.lower()}:{operation.name.lower()}",
                        redact(
                            {
                                "connector_id": connector.id,
                                "connector": connector.name,
                                "operation_id": operation.id,
                                "operation": operation.name,
                                "description": operation.description[:220],
                                "risk_level": operation.risk_level,
                                "requires_approval": operation.requires_approval_default,
                                "auth_status": auth_status,
                                "action_category": operation.action_category,
                            }
                        ),
                    )
                )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in candidates[:limit]]


def _score(message: str, *fields: str) -> int:
    normalized = _normalize(message)
    haystack = _normalize(" ".join(fields))
    tokens = [token for token in re.split(r"\W+", normalized) if len(token) > 2]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 2
    hints = {
        "api": ["api", "http", "openapi"],
        "github": ["github", "repo", "issue", "pull"],
        "issue": ["github", "issue"],
        "repo": ["github", "repo", "filesystem"],
        "fichier": ["filesystem", "workspace"],
        "file": ["filesystem", "workspace"],
        "http": ["http", "api"],
        "connecteur": ["api", "connector"],
        "connector": ["api", "connector"],
    }
    for keyword, terms in hints.items():
        if keyword in normalized and any(term in haystack for term in terms):
            score += 8
    return score


def _normalize(value: str) -> str:
    import unicodedata

    lowered = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in lowered if not unicodedata.combining(char))
