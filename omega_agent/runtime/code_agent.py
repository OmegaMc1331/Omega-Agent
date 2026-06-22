from __future__ import annotations

from typing import TYPE_CHECKING

from omega_agent.config import OmegaConfig

if TYPE_CHECKING:
    from omega_agent.runtime.patch_planner import PatchPlanner
    from omega_agent.runtime.repo_analyzer import RepoProfilesStore
    from omega_agent.runtime.self_healing import SelfHealingEngine
    from omega_agent.runtime.test_runner import CodeTestRunner


class CodeWorkspaceAgent:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self._repo_profiles: RepoProfilesStore | None = None
        self._tests: CodeTestRunner | None = None
        self._patch_planner: PatchPlanner | None = None
        self._self_healing: SelfHealingEngine | None = None

    @property
    def repo_profiles(self) -> RepoProfilesStore:
        if self._repo_profiles is None:
            from omega_agent.runtime.repo_analyzer import RepoProfilesStore

            self._repo_profiles = RepoProfilesStore(self.config)
        return self._repo_profiles

    @property
    def tests(self) -> CodeTestRunner:
        if self._tests is None:
            from omega_agent.runtime.test_runner import CodeTestRunner

            self._tests = CodeTestRunner(self.config)
        return self._tests

    @property
    def patch_planner(self) -> PatchPlanner:
        if self._patch_planner is None:
            from omega_agent.runtime.patch_planner import PatchPlanner

            self._patch_planner = PatchPlanner(self.config)
        return self._patch_planner

    @property
    def self_healing(self) -> SelfHealingEngine:
        if self._self_healing is None:
            from omega_agent.runtime.self_healing import SelfHealingEngine

            self._self_healing = SelfHealingEngine(self.config)
        return self._self_healing

    def scan(self, project_id: str | None = None) -> dict:
        return self.repo_profiles.scan(project_id=project_id).as_api()

    def test(self, command: str | None = None, project_id: str | None = None) -> dict:
        result = self.tests.run_command(command, project_id=project_id) if command else self.tests.run_detected_tests(project_id=project_id)
        payload = result.as_api()
        if result.status != "passed":
            from omega_agent.runtime.error_taxonomy import classify_error

            classified = classify_error(f"{result.stdout}\n{result.stderr}\n{result.summary}", {"command": result.command, "test_run_id": result.id})
            payload["classified_error"] = classified.as_api()
            payload["recovery"] = self.self_healing.suggest_recovery(classified.error_type, {"command": result.command}).as_api()
        return payload

    def diff(self) -> dict:
        return self.patch_planner.produce_diff_summary()
