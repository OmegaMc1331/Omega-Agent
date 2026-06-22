from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact
from omega_agent.shadow.shadow_workspace import ShadowWorkspace, fingerprint, is_sensitive_shadow_path


def collect_predicted_diff(config: OmegaConfig, shadow_run_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    shadow = ShadowWorkspace(config, shadow_run_id)
    paths = _candidate_paths(shadow, plan)
    created: list[dict[str, Any]] = []
    modified: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    for relative in sorted(paths):
        if is_sensitive_shadow_path(relative):
            continue
        real_path = (config.workspace / relative).resolve()
        shadow_path = (shadow.workspace / relative).resolve()
        before = fingerprint(real_path)
        after = fingerprint(shadow_path)
        if before == after:
            continue
        item = {
            "path": relative,
            "before": before,
            "after": after,
            "diff": _text_diff(real_path, shadow_path),
            "risk": _file_risk(relative, before, after),
        }
        if not before.get("exists") and after.get("exists"):
            created.append(item)
        elif before.get("exists") and not after.get("exists"):
            deleted.append(item)
        else:
            modified.append(item)
    summary = f"{len(created)} créé(s), {len(modified)} modifié(s), {len(deleted)} supprimé(s)"
    return redact({"created": created, "modified": modified, "deleted": deleted, "summary": summary})


def _candidate_paths(shadow: ShadowWorkspace, plan: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for step in plan.get("steps") or []:
        args = step.get("arguments") or {}
        for key in ("relative_path", "source_path", "destination_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.replace("\\", "/"))
    if shadow.workspace.exists():
        for child in shadow.workspace.rglob("*"):
            if child.is_file():
                relative = child.relative_to(shadow.workspace).as_posix()
                if relative == ".omega" or relative.startswith(".omega/"):
                    continue
                paths.add(relative)
    return paths


def _text_diff(before: Path, after: Path) -> str:
    if (before.exists() and not before.is_file()) or (after.exists() and not after.is_file()):
        return ""
    try:
        before_lines = before.read_text(encoding="utf-8", errors="replace").splitlines() if before.exists() else []
        after_lines = after.read_text(encoding="utf-8", errors="replace").splitlines() if after.exists() else []
    except OSError:
        return ""
    diff = difflib.unified_diff(before_lines, after_lines, fromfile=f"a/{before.name}", tofile=f"b/{after.name}", lineterm="")
    return "\n".join(list(diff)[:4000])


def _file_risk(relative: str, before: dict[str, Any], after: dict[str, Any]) -> str:
    lowered = relative.lower()
    if not after.get("exists"):
        return "high"
    if any(name in lowered for name in ("pyproject.toml", "package.json", "config", "policy", "security")):
        return "medium"
    return "low"
