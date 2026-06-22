from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact


def load_eval_dataset(config: OmegaConfig, path_or_name: str) -> dict:
    path = resolve_dataset_path(config, path_or_name)
    if not path.exists():
        raise FileNotFoundError(f"Dataset eval introuvable: {path_or_name}")
    if path.suffix.lower() == ".jsonl":
        cases = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped:
                cases.append(_normalize_case(json.loads(stripped)))
        return {"name": path.stem, "description": "", "cases": redact(cases), "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return {"name": path.stem, "description": "", "cases": [_normalize_case(item) for item in data], "path": str(path)}
    if not isinstance(data, dict):
        raise ValueError("Dataset eval invalide.")
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    return {
        "name": str(data.get("name") or path.stem),
        "description": str(data.get("description") or ""),
        "cases": redact([_normalize_case(item) for item in cases if isinstance(item, dict)]),
        "path": str(path),
    }


def resolve_dataset_path(config: OmegaConfig, path_or_name: str) -> Path:
    raw = Path(path_or_name).expanduser()
    if raw.exists():
        return raw.resolve()
    base = config.evals_default_dataset_dir or (Path.home() / ".omega" / "evals")
    candidates = [base / path_or_name, base / f"{path_or_name}.json", base / f"{path_or_name}.jsonl"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _normalize_case(item: dict[str, Any]) -> dict:
    prompt = str(item.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Chaque eval case doit contenir prompt.")
    return {
        "name": str(item.get("name") or prompt[:60]),
        "prompt": prompt,
        "expected_outcome": item.get("expected_outcome"),
        "expected_files_created": _string_list(item.get("expected_files_created")),
        "expected_files_modified": _string_list(item.get("expected_files_modified")),
        "expected_contains": item.get("expected_contains"),
        "expected_denied": bool(item.get("expected_denied", False)),
        "expected_tool_calls": _string_list(item.get("expected_tool_calls")),
        "project_setup": item.get("project_setup") if isinstance(item.get("project_setup"), dict) else {},
        "project_id": item.get("project_id"),
        "agent_profile_id": item.get("agent_profile_id"),
        "model_ref": item.get("model_ref"),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []
