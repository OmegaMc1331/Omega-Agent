from __future__ import annotations

from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.project_memory import ProjectMemoryStore
from omega_agent.skills.skill_store import SkillStore
from omega_agent.skills.skill_tests import SkillTests
from omega_agent.skills.skill_validator import SkillValidator
from omega_agent.workflows.workflow_store import WorkflowStore


class SkillPromoter:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = SkillStore(config)
        self.events = EventsStore(config)
        self.validator = SkillValidator(config)

    def accept_candidate(self, candidate_id: str):
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError("Candidate introuvable.")
        if candidate.status != "pending":
            raise ValueError("Candidate non pending.")
        proposed = candidate.proposed_skill
        definition = proposed.get("definition") or {}
        test_cases = proposed.get("test_cases") or []
        validation = self.validator.validate(definition, test_cases)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        untrusted = bool(candidate.metadata.get("untrusted"))
        skill = self.store.create_skill(
            name=str(proposed.get("name") or definition.get("name") or candidate.title),
            description=str(proposed.get("description") or candidate.description),
            skill_type=str(proposed.get("skill_type") or "tool_recipe"),
            definition=definition,
            test_cases=test_cases,
            source_candidate_id=candidate.id,
            status="draft",
            metadata={
                "trust_level": "untrusted" if untrusted else "local",
                "source_run_ids": candidate.source_run_ids,
                "source_workflow_ids": candidate.source_workflow_ids,
            },
        )
        self.store.update_candidate_status(candidate.id, "accepted")
        self.events.add("skill.candidate.accepted", {"candidate_id": candidate.id, "skill_id": skill.id})
        self.events.add("skill.created", {"candidate_id": candidate.id, "skill_id": skill.id, "status": "draft"})
        self._record_memory(skill, candidate)
        if skill.skill_type == "workflow":
            self._create_workflow_template(skill)
        return skill

    def reject_candidate(self, candidate_id: str):
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError("Candidate introuvable.")
        rejected = self.store.update_candidate_status(candidate_id, "rejected")
        self.events.add("skill.candidate.rejected", {"candidate_id": candidate_id})
        return rejected

    def test_skill(self, skill_id: str):
        return SkillTests(self.config).run(skill_id)

    def activate(self, skill_id: str):
        skill = self.store.get_skill(skill_id)
        if skill is None:
            raise ValueError("Skill introuvable.")
        validation = self.validator.validate(skill.definition, skill.test_cases)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        if self.config.skills_test_before_activation:
            latest = self.store.latest_test_run(skill.id, skill.version)
            if latest is None or latest.status != "passed":
                raise ValueError("Un test passed pour cette version est requis avant activation.")
        activated = self.store.set_status(skill.id, "active")
        if skill.source_candidate_id:
            self.store.update_candidate_status(skill.source_candidate_id, "promoted")
        capabilities = CapabilitiesRegistry(self.config)
        capabilities.refresh()
        capabilities.enable(f"skill:{skill.id}")
        self.events.add("skill.activated", {"skill_id": skill.id, "version": skill.version})
        return activated

    def disable(self, skill_id: str):
        skill = self.store.set_status(skill_id, "disabled")
        if skill is None:
            raise ValueError("Skill introuvable.")
        capabilities = CapabilitiesRegistry(self.config)
        capabilities.refresh()
        capabilities.disable(f"skill:{skill.id}")
        self.events.add("skill.disabled", {"skill_id": skill.id, "version": skill.version})
        return skill

    def _record_memory(self, skill, candidate) -> None:
        if not self.config.memory_enabled or not self.config.memory_project_memory_enabled:
            return
        try:
            ProjectMemoryStore(self.config).create_memory(
                scope="global",
                content=f"Skill Foundry draft created: {skill.name} ({skill.version}). It remains inactive until tested and approved.",
                type="decision",
                provenance={
                    "source_type": "run" if candidate.source_run_ids else "workflow",
                    "source_id": (candidate.source_run_ids or candidate.source_workflow_ids or [candidate.id])[0],
                    "source_label": "Omega Skill Foundry candidate",
                    "metadata": {"candidate_id": candidate.id, "skill_id": skill.id},
                },
                tags=["skill-foundry", "skill", "provenance"],
                confidence=candidate.confidence,
                key=f"skill-foundry:{skill.slug}:{skill.version}",
                created_by="omega",
                summary=f"Draft skill {skill.name} created from reviewed successful trajectories.",
                metadata={"skill_id": skill.id, "candidate_id": candidate.id},
            )
        except (ValueError, PermissionError):
            return

    def _create_workflow_template(self, skill) -> None:
        definition = skill.definition
        steps = []
        for item in definition.get("steps") or []:
            action = str(item.get("action") or "")
            if not action:
                continue
            steps.append(
                {
                    "id": f"step-{len(steps) + 1}",
                    "type": "tool",
                    "name": str(item.get("instruction") or action),
                    "tool": action,
                    "arguments": {},
                    "on_error": "ask_user",
                }
            )
        steps.append({"id": "final", "type": "final", "name": "Summary", "message": "Skill workflow completed."})
        WorkflowStore(self.config).create_template(
            template_id=f"skill-{skill.id}",
            name=skill.name,
            description=skill.description,
            category="skill",
            definition={"name": skill.name, "description": skill.description, "version": skill.version, "steps": steps},
            metadata={"source_skill_id": skill.id, "generated": True, "enabled": False},
        )
