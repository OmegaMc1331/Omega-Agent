from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.skills.skill_store import SkillStore
from omega_agent.skills.skill_validator import SkillValidator


class SkillTests:
    """Safe v1 tests: schema, capability, policy and secret checks only."""

    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = SkillStore(config)
        self.validator = SkillValidator(config)
        self.events = EventsStore(config)

    def run(self, skill_id: str):
        skill = self.store.get_skill(skill_id)
        if skill is None:
            raise ValueError("Skill introuvable.")
        self.events.add("skill.test.started", {"skill_id": skill.id, "version": skill.version})
        try:
            validation = self.validator.validate(skill.definition, skill.test_cases)
            status = "passed" if validation.valid else "failed"
            result = self.store.add_test_run(
                skill.id,
                skill.version,
                status,
                {
                    "validation": validation.as_api(),
                    "tests": [
                        {
                            "name": str(test.get("name") or "unnamed"),
                            "status": "passed" if validation.valid else "failed",
                            "type": str(test.get("type") or "static"),
                        }
                        for test in skill.test_cases
                    ],
                    "executed_commands": [],
                },
                {"safe_static_validation": True},
            )
        except Exception as exc:
            result = self.store.add_test_run(
                skill.id,
                skill.version,
                "error",
                {"error": str(exc), "executed_commands": []},
                {"safe_static_validation": True},
            )
        self.events.add("skill.test.completed", {"skill_id": skill.id, "version": skill.version, "status": result.status})
        return result
