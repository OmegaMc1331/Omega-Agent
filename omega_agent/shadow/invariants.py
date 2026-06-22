from __future__ import annotations

from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.shadow.shadow_workspace import ShadowWorkspace, is_sensitive_shadow_path


def verify_invariants(config: OmegaConfig, shadow_run_id: str, plan: dict[str, Any], step_results: list[dict[str, Any]]) -> dict[str, Any]:
    workspace = ShadowWorkspace(config, shadow_run_id)
    unchanged, changed_paths = workspace.verify_real_workspace_unchanged()
    sensitive_paths = []
    for step in plan.get("steps") or []:
        for value in (step.get("arguments") or {}).values():
            if isinstance(value, str) and is_sensitive_shadow_path(value):
                sensitive_paths.append(value)
    external_executed = [
        item
        for item in step_results
        if item.get("action_category") == "external_side_effect" and item.get("status") == "succeeded" and not item.get("simulated")
    ]
    checks = {
        "real_workspace_unchanged": {"passed": unchanged, "details": changed_paths},
        "no_external_write": {"passed": not external_executed, "details": external_executed},
        "no_sensitive_path_copy": {"passed": not sensitive_paths, "details": sensitive_paths},
        "simulation_marked": {"passed": all(bool(item.get("simulated")) for item in step_results), "details": []},
    }
    return {"passed": all(item["passed"] for item in checks.values()), "checks": checks}
