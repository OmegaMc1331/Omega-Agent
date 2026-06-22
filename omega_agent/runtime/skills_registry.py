from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfile, filter_skills_for_profile

SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    tools: list[str]
    risk: str
    tags: list[str]
    enabled: bool
    path: str
    id: str = ""
    version: str = "0.1.0"
    risk_level: str = "low"
    allowed_tools: list[str] | None = None
    status: str = "active"
    skill_type: str = "prompt"
    definition: dict | None = None
    test_cases: list[dict] | None = None
    source_candidate_id: str | None = None
    metadata: dict | None = None

    def __post_init__(self):
        if not self.id:
            object.__setattr__(self, "id", self.name)
        if self.risk_level == "low" and self.risk != "low":
            object.__setattr__(self, "risk_level", self.risk)
        if self.allowed_tools is None:
            object.__setattr__(self, "allowed_tools", self.tools)


class SkillsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.root = config.skills_dir or Path("~/omega_skills").expanduser()

    def list(self) -> list[Skill]:
        skills: list[Skill] = []
        if self.root.exists():
            for child in sorted(self.root.iterdir()):
                if child.is_dir():
                    skill = self._load(child)
                    if skill:
                        skills.append(skill)
        foundry_ids = {skill.id for skill in skills}
        for skill in self._load_foundry():
            if skill.id not in foundry_ids:
                skills.append(skill)
        return skills

    def list_for_profile(self, profile: AgentProfile) -> list[Skill]:
        return filter_skills_for_profile([skill for skill in self.list() if skill.enabled], profile)

    def create(
        self,
        name: str,
        description: str,
        instructions: str = "",
        tools: list[str] | None = None,
        risk: str = "low",
        tags: list[str] | None = None,
    ) -> Skill:
        if not SAFE_NAME.match(name):
            raise ValueError("Nom de skill invalide.")
        target = self.root / name
        target.mkdir(parents=True, exist_ok=False)
        metadata = {
            "id": name,
            "name": name,
            "description": description,
            "version": "0.1.0",
            "risk_level": risk,
            "enabled": True,
            "allowed_tools": tools or [],
            "tags": tags or [],
        }
        (target / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "skill.md").write_text(instructions or f"# {name}\n\n{description}\n", encoding="utf-8")
        loaded = self._load(target)
        if loaded is None:
            raise RuntimeError("Skill creee mais non chargeable.")
        return loaded

    def set_enabled(self, name: str, enabled: bool) -> Skill | None:
        foundry = self._find_foundry(name)
        if foundry is not None:
            from omega_agent.skills.skill_promoter import SkillPromoter

            changed = SkillPromoter(self.config).activate(foundry.id) if enabled else SkillPromoter(self.config).disable(foundry.id)
            return self._from_stored(changed) if changed else None
        if not SAFE_NAME.match(name):
            raise ValueError("Nom de skill invalide.")
        target = self.root / name
        metadata_path = target / "metadata.json"
        if not metadata_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["enabled"] = enabled
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._load(target)

    def delete(self, name: str) -> bool:
        foundry = self._find_foundry(name)
        if foundry is not None:
            from omega_agent.skills.skill_store import SkillStore

            return SkillStore(self.config).archive_skill(foundry.id)
        if not SAFE_NAME.match(name):
            raise ValueError("Nom de skill invalide.")
        target = self.root / name
        if not target.exists() or not target.is_dir():
            return False
        for path in (target / "metadata.json", target / "skill.md"):
            if path.exists():
                path.unlink()
        target.rmdir()
        return True

    def _load(self, path: Path) -> Skill | None:
        metadata_path = path / "metadata.json"
        skill_path = path / "skill.md"
        if not metadata_path.exists() or not skill_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        allowed_tools = list(metadata.get("allowed_tools") or metadata.get("tools") or [])
        risk = str(metadata.get("risk_level") or metadata.get("risk") or "low")
        return Skill(
            id=str(metadata.get("id") or path.name),
            name=str(metadata.get("name") or path.name),
            description=str(metadata.get("description") or ""),
            version=str(metadata.get("version") or "0.1.0"),
            instructions=skill_path.read_text(encoding="utf-8", errors="replace"),
            tools=allowed_tools,
            allowed_tools=allowed_tools,
            risk=risk,
            risk_level=risk,
            tags=list(metadata.get("tags") or []),
            enabled=bool(metadata.get("enabled", True)),
            path=str(path),
            status="active" if bool(metadata.get("enabled", True)) else "disabled",
            skill_type=str(metadata.get("skill_type") or "prompt"),
            metadata=metadata,
        )

    def _load_foundry(self) -> list[Skill]:
        if not getattr(self.config, "skills_enabled", True):
            return []
        try:
            from omega_agent.skills.skill_store import SkillStore

            return [self._from_stored(item) for item in SkillStore(self.config).list_skills()]
        except Exception:
            return []

    def _find_foundry(self, identifier: str):
        try:
            from omega_agent.skills.skill_store import SkillStore

            return SkillStore(self.config).get_skill(identifier)
        except Exception:
            return None

    @staticmethod
    def _from_stored(item) -> Skill:
        steps = item.definition.get("steps") or []
        instructions = "\n".join(
            f"{step.get('order', index + 1)}. {step.get('instruction') or step.get('action') or 'Review step'}"
            for index, step in enumerate(steps)
        )
        return Skill(
            id=item.id,
            name=item.name,
            description=item.description,
            version=item.version,
            instructions=instructions,
            tools=list(item.allowed_tools or []),
            allowed_tools=list(item.allowed_tools or []),
            risk=item.risk_level,
            risk_level=item.risk_level,
            tags=["foundry", item.skill_type],
            enabled=item.status == "active" and item.enabled,
            path=f"db://skills/{item.id}",
            status=item.status,
            skill_type=item.skill_type,
            definition=item.definition,
            test_cases=item.test_cases,
            source_candidate_id=item.source_candidate_id,
            metadata=item.metadata,
        )
