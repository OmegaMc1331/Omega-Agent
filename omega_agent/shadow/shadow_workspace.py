from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.security.redaction import redact

SENSITIVE_PARTS = {
    ".env",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "cookies",
    "login data",
}
SENSITIVE_FRAGMENTS = {"secret", "token", "password", "passwd", "credential"}


class ShadowWorkspace:
    def __init__(self, config: OmegaConfig, shadow_run_id: str):
        self.config = config
        self.shadow_run_id = shadow_run_id
        self.root = (config.workspace / ".omega" / "shadow" / shadow_run_id).resolve()
        self.workspace = self.root / "workspace"
        self.manifest_path = self.root / "manifest.json"

    def prepare(self, plan: dict[str, Any]) -> Path:
        self._assert_controlled_root()
        if self.root.exists():
            shutil.rmtree(self.root)
        self.workspace.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        baseline: dict[str, Any] = {}
        for relative in sorted(_plan_paths(plan)):
            safe_relative = validate_shadow_relative_path(relative)
            source = (self.config.workspace / safe_relative).resolve()
            target = (self.workspace / safe_relative).resolve()
            if not _inside(target, self.workspace):
                raise PermissionError("Chemin shadow hors workspace isolé.")
            if source.exists():
                if is_sensitive_shadow_path(safe_relative):
                    raise PermissionError(f"Copie shadow refusée pour chemin sensible: {safe_relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target, ignore=_ignore_sensitive)
                else:
                    shutil.copy2(source, target)
                copied.append(safe_relative)
            baseline[safe_relative] = fingerprint(source)
        manifest = {
            "shadow_run_id": self.shadow_run_id,
            "real_workspace": str(self.config.workspace),
            "shadow_workspace": str(self.workspace),
            "copied_paths": copied,
            "baseline": baseline,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.manifest_path.write_text(json.dumps(redact(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
        return self.workspace

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def verify_real_workspace_unchanged(self) -> tuple[bool, list[str]]:
        changed: list[str] = []
        manifest = self.load_manifest()
        for relative, before in (manifest.get("baseline") or {}).items():
            current = fingerprint((self.config.workspace / relative).resolve())
            if current != before:
                changed.append(relative)
        return not changed, changed

    def cleanup(self) -> None:
        self._assert_controlled_root()
        if self.root.exists():
            shutil.rmtree(self.root)

    @classmethod
    def expire_old(cls, config: OmegaConfig) -> list[str]:
        root = (config.workspace / ".omega" / "shadow").resolve()
        if not root.exists():
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, int(config.shadow_workspace_keep_days)))
        expired: list[str] = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                shutil.rmtree(child)
                expired.append(child.name)
        return expired

    def _assert_controlled_root(self) -> None:
        expected = (self.config.workspace / ".omega" / "shadow").resolve()
        if not _inside(self.root, expected) or self.root == expected:
            raise PermissionError("Racine shadow non contrôlée.")


def validate_shadow_relative_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise PermissionError("Chemin shadow invalide.")
    if is_sensitive_shadow_path(normalized):
        raise PermissionError("Chemin sensible refusé en shadow.")
    return path.as_posix()


def is_sensitive_shadow_path(value: str) -> bool:
    parts = [part.lower() for part in PurePosixPath(str(value).replace("\\", "/")).parts]
    return any(part in SENSITIVE_PARTS or any(fragment in part for fragment in SENSITIVE_FRAGMENTS) for part in parts)


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    if path.is_dir():
        entries: list[tuple[str, str]] = []
        for child in sorted(path.rglob("*")):
            if child.is_file() and not is_sensitive_shadow_path(child.relative_to(path).as_posix()):
                entries.append((child.relative_to(path).as_posix(), _hash_file(child)))
        return {"exists": True, "kind": "directory", "entries": entries}
    return {"exists": True, "kind": "file", "size": path.stat().st_size, "sha256": _hash_file(path)}


def _plan_paths(plan: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for step in plan.get("steps") or []:
        args = step.get("arguments") or {}
        for key in ("relative_path", "source_path", "destination_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value)
    return paths


def _ignore_sensitive(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if is_sensitive_shadow_path(name)}


def _inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
