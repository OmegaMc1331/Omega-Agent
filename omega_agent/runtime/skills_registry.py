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
        if not self.root.exists():
            return []
        skills: list[Skill] = []
        for child in sorted(self.root.iterdir()):
            if child.is_dir():
                skill = self._load(child)
                if skill:
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
        )
