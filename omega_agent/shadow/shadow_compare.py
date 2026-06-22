from __future__ import annotations

from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.shadow.shadow_workspace import ShadowWorkspace, fingerprint


def compare_shadow_to_live(config: OmegaConfig, shadow_run_id: str, predicted_diff: dict[str, Any]) -> dict[str, Any]:
    shadow = ShadowWorkspace(config, shadow_run_id)
    paths = [
        str(item.get("path") or "")
        for group in ("created", "modified", "deleted")
        for item in (predicted_diff.get(group) or [])
        if item.get("path")
    ]
    comparisons: list[dict[str, Any]] = []
    matches = 0
    for relative in paths:
        shadow_state = fingerprint((shadow.workspace / relative).resolve())
        live_state = fingerprint((config.workspace / relative).resolve())
        matched = shadow_state == live_state
        matches += int(matched)
        comparisons.append({"path": relative, "matched": matched, "shadow": shadow_state, "live": live_state})
    score = 1.0 if not paths else matches / len(paths)
    return {
        "files": comparisons,
        "success_match": score == 1.0,
        "diff_match_score": round(score, 4),
        "summary": f"{matches}/{len(paths)} fichier(s) conformes au shadow",
    }
