from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omega_agent.security.redaction import redact

SOURCE_TYPES = {"user_message", "assistant_message", "run", "tool", "file", "manual", "imported"}


@dataclass(frozen=True)
class ProvenanceInput:
    source_type: str
    source_id: str | None = None
    source_label: str | None = None
    quote: str | None = None
    metadata: dict | None = None

    def as_json(self) -> dict:
        return redact(
            {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "source_label": self.source_label,
                "quote": self.quote,
                "metadata": self.metadata or {},
            }
        )


def normalize_provenance(provenance: Any) -> list[ProvenanceInput]:
    if provenance is None or provenance == {} or provenance == []:
        return []
    items = provenance if isinstance(provenance, list) else [provenance]
    normalized: list[ProvenanceInput] = []
    for item in items:
        if isinstance(item, ProvenanceInput):
            source_type = item.source_type
            data = item
        elif isinstance(item, dict):
            source_type = str(item.get("source_type") or "manual")
            data = ProvenanceInput(
                source_type=source_type,
                source_id=_optional_str(item.get("source_id")),
                source_label=_optional_str(item.get("source_label")),
                quote=_optional_str(item.get("quote")),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        else:
            source_type = "manual"
            data = ProvenanceInput(source_type=source_type, source_label=str(item))
        if source_type not in SOURCE_TYPES:
            raise ValueError("Type de provenance invalide.")
        normalized.append(data)
    return normalized


def default_manual_provenance(label: str = "manual") -> dict:
    return {"source_type": "manual", "source_label": label}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
