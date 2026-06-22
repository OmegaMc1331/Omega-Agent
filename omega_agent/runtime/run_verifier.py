from __future__ import annotations

from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.runtime.patch_planner import PatchPlanner
from omega_agent.runtime.test_runner import CodeTestRunner, TestRunResult


def verify_workspace_state(config: OmegaConfig, *, run_tests: bool = True, project_id: str | None = None) -> dict:
    diff = PatchPlanner(config).produce_diff_summary()
    test_run: TestRunResult | None = CodeTestRunner(config).run_detected_tests(project_id=project_id) if run_tests else None
    return {
        "workspace": str(Path(config.workspace).resolve()),
        "diff": {key: value for key, value in diff.items() if key != "diff"},
        "test_run": test_run.as_api() if test_run else None,
        "ok": (test_run is None or test_run.status == "passed"),
    }
