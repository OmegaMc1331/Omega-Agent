from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.security.plugin_policy import (
    MAX_MARKDOWN_BYTES,
    enabled_allowed,
    load_plugin_json,
    security_review_for_manifest,
    validate_plugin_file,
)


@dataclass(frozen=True)
class PluginManifest:
    name: str
    tools: list[dict]
    skills: list[dict]
    channels: list[str]
    hooks: list[str]
    status: str
    path: str
    id: str = ""
    version: str = "0.1.0"
    description: str = ""
    enabled: bool = False
    trust_level: str = "untrusted"
    declares: dict | None = None
    author: str = ""
    permissions: list[str] | None = None
    raw_manifest: dict | None = None
    readme: str = ""
    skills_markdown: dict | None = None
    security_review: dict | None = None
    error: str = ""

    def __post_init__(self):
        if not self.id:
            object.__setattr__(self, "id", self.name)
        if self.declares is None:
            object.__setattr__(self, "declares", {"tools": self.tools, "skills": self.skills, "channels": self.channels, "hooks": self.hooks})
        if self.permissions is None:
            object.__setattr__(self, "permissions", [])
        if self.raw_manifest is None:
            object.__setattr__(self, "raw_manifest", {})
        if self.skills_markdown is None:
            object.__setattr__(self, "skills_markdown", {})
        if self.security_review is None:
            object.__setattr__(self, "security_review", {})


class PluginsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.root = (config.plugins_dir or Path("~/omega_plugins").expanduser()).expanduser()

    def list(self) -> list[PluginManifest]:
        if not self.root.exists():
            return []
        plugins: list[PluginManifest] = []
        for child in sorted(self.root.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            plugins.append(self._load_plugin(child))
        return plugins

    def get(self, plugin_id: str) -> PluginManifest | None:
        return next((plugin for plugin in self.list() if plugin.id == plugin_id), None)

    def security_review(self, plugin_id: str) -> dict | None:
        plugin = self.get(plugin_id)
        return plugin.security_review if plugin else None

    def rescan(self) -> list[PluginManifest]:
        return self.list()

    def set_enabled(self, plugin_id: str, enabled: bool, confirmed: bool = False) -> PluginManifest | None:
        plugin = self.get(plugin_id)
        if plugin is None:
            return None
        if plugin.status != "loaded":
            raise ValueError(plugin.error or "Plugin non chargeable.")
        data = dict(plugin.raw_manifest or {})
        if enabled:
            allowed, reason = enabled_allowed(data, confirmed=confirmed)
            if not allowed:
                raise ValueError(reason)
        manifest_path = Path(plugin.path)
        data["enabled"] = enabled
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get(plugin_id)

    def _load_plugin(self, plugin_dir: Path) -> PluginManifest:
        manifest_path = plugin_dir / "plugin.json"
        try:
            data = load_plugin_json(self.root, plugin_dir)
            raw_data = dict(data)
            review = security_review_for_manifest(data)
            status = "loaded"
            if any("code executable" in warning for warning in review.critical_warnings):
                data["trust_level"] = "blocked"
                status = "blocked"
                review = security_review_for_manifest(data, status=status)
            if data["trust_level"] == "blocked":
                status = "blocked"
                review = security_review_for_manifest(data, status=status)
                data["enabled"] = False
            if data["trust_level"] in {"untrusted", "blocked"}:
                data["enabled"] = False
            if review.critical_warnings:
                data["enabled"] = False
            declares = dict(data.get("declares") or {})
            readme = _read_optional_markdown(self.root, plugin_dir, plugin_dir / "README.md")
            skill_markdown = _read_skill_markdown(self.root, plugin_dir)
            return PluginManifest(
                id=str(data["id"]),
                name=str(data["name"]),
                version=str(data["version"]),
                description=str(data["description"]),
                author=str(data.get("author") or ""),
                enabled=bool(data.get("enabled", False)),
                trust_level=str(data["trust_level"]),
                permissions=[str(item) for item in data.get("permissions") or []],
                declares=declares,
                tools=list(declares.get("tools") or []),
                skills=list(declares.get("skills") or []),
                channels=list(declares.get("channels") or []),
                hooks=list(declares.get("hooks") or []),
                status=status,
                path=str(manifest_path),
                raw_manifest=raw_data,
                readme=readme,
                skills_markdown=skill_markdown,
                security_review=review.as_api(),
            )
        except Exception as exc:
            review = security_review_for_manifest({"trust_level": "blocked", "permissions": []}, status="rejected").as_api()
            review["critical_warnings"] = [str(exc)]
            return PluginManifest(
                id=plugin_dir.name,
                name=plugin_dir.name,
                tools=[],
                skills=[],
                channels=[],
                hooks=[],
                status="rejected",
                path=str(manifest_path),
                enabled=False,
                trust_level="blocked",
                declares={"tools": [], "skills": [], "channels": [], "hooks": []},
                raw_manifest={},
                security_review=review,
                error=str(exc),
            )


def _read_optional_markdown(root: Path, plugin_dir: Path, path: Path) -> str:
    if not path.exists():
        return ""
    try:
        resolved = validate_plugin_file(root, plugin_dir, path, MAX_MARKDOWN_BYTES)
    except Exception:
        return ""
    return resolved.read_text(encoding="utf-8", errors="replace")


def _read_skill_markdown(root: Path, plugin_dir: Path) -> dict[str, str]:
    skills_dir = plugin_dir / "skills"
    if not skills_dir.exists() or not skills_dir.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(skills_dir.glob("*.md")):
        try:
            resolved = validate_plugin_file(root, plugin_dir, path, MAX_MARKDOWN_BYTES)
        except Exception:
            continue
        result[path.name] = resolved.read_text(encoding="utf-8", errors="replace")
    return result
