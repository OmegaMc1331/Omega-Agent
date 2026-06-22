from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_workflow_json(payload: str | bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Workflow JSON invalide.") from exc
    if not isinstance(value, dict):
        raise ValueError("Workflow JSON doit contenir un objet.")
    return value


def load_workflow_file(path: str | Path) -> dict[str, Any]:
    return parse_workflow_json(Path(path).read_text(encoding="utf-8-sig"))
