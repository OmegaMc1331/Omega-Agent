from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

TRUST_LEVELS = {"builtin", "local", "untrusted", "blocked"}
PERMISSIONS = {
    "tools.register",
    "skills.register",
    "channels.register",
    "hooks.register",
    "filesystem.read",
    "filesystem.write",
    "shell.execute",
    "network.access",
    "browser.control",
    "desktop.control",
}
DECLARATION_KEYS = {"tools", "skills", "channels", "hooks"}
EXECUTABLE_MANIFEST_KEYS = {"entrypoint", "command", "commands", "script", "scripts", "module", "python", "node", "executable"}
MAX_MANIFEST_BYTES = 256 * 1024
MAX_MARKDOWN_BYTES = 256 * 1024


@dataclass(frozen=True)
class PluginSecurityReview:
    status: str
    risk_level: str
    warnings: list[str]
    critical_warnings: list[str]
    permissions: list[str]
    trust_level: str
    manifest_only: bool = True
    code_execution_allowed: bool = False

    def as_api(self) -> dict:
        return {
            "status": self.status,
            "risk_level": self.risk_level,
            "warnings": self.warnings,
            "critical_warnings": self.critical_warnings,
            "permissions": self.permissions,
            "trust_level": self.trust_level,
            "manifest_only": self.manifest_only,
            "code_execution_allowed": self.code_execution_allowed,
        }


def validate_plugin_dir(root: Path, plugin_dir: Path) -> Path:
    root = root.expanduser().resolve()
    candidate = plugin_dir
    if candidate.is_symlink():
        resolved = candidate.resolve()
        if os.path.commonpath([str(root), str(resolved)]) != str(root):
            raise PermissionError("Symlink plugin hors dossier plugins refuse.")
    resolved = candidate.resolve()
    if os.path.commonpath([str(root), str(resolved)]) != str(root):
        raise PermissionError("Chemin plugin hors dossier plugins refuse.")
    if ".." in candidate.as_posix().split("/"):
        raise PermissionError("Path traversal plugin refuse.")
    return resolved


def validate_plugin_file(root: Path, plugin_dir: Path, file_path: Path, max_bytes: int) -> Path:
    validate_plugin_dir(root, plugin_dir)
    resolved = file_path.resolve()
    plugin_root = plugin_dir.resolve()
    if os.path.commonpath([str(plugin_root), str(resolved)]) != str(plugin_root):
        raise PermissionError("Fichier plugin hors dossier plugin refuse.")
    if resolved.stat().st_size > max_bytes:
        raise ValueError("Fichier plugin trop volumineux.")
    return resolved


def load_plugin_json(root: Path, plugin_dir: Path) -> dict:
    manifest_path = validate_plugin_file(root, plugin_dir, plugin_dir / "plugin.json", MAX_MANIFEST_BYTES)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Manifest plugin JSON invalide.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Manifest plugin invalide: objet JSON requis.")
    payload = normalize_manifest(payload)
    validate_manifest_schema(payload)
    return payload


def normalize_manifest(data: dict) -> dict:
    payload = dict(data)
    payload.setdefault("version", "0.1.0")
    payload.setdefault("description", "")
    payload.setdefault("author", "")
    payload.setdefault("enabled", False)
    payload.setdefault("trust_level", "untrusted")
    payload.setdefault("permissions", [])
    declares = payload.get("declares")
    if not isinstance(declares, dict):
        declares = {}
    payload["declares"] = {key: list(declares.get(key) or []) for key in DECLARATION_KEYS}
    return payload


def validate_manifest_schema(data: dict) -> None:
    required = {"id", "name", "version", "enabled", "trust_level", "permissions", "declares"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Manifest plugin invalide: champs manquants {', '.join(missing)}.")
    for key in ("id", "name", "version", "trust_level"):
        if not isinstance(data.get(key), str) or not str(data.get(key)).strip():
            raise ValueError(f"Manifest plugin invalide: {key} doit etre une chaine non vide.")
    if not isinstance(data.get("description"), str):
        raise ValueError("Manifest plugin invalide: description doit etre une chaine.")
    if not isinstance(data.get("enabled"), bool):
        raise ValueError("Manifest plugin invalide: enabled doit etre booleen.")
    if data["trust_level"] not in TRUST_LEVELS:
        raise ValueError("Manifest plugin invalide: trust_level inconnu.")
    if not isinstance(data.get("permissions"), list) or not all(isinstance(item, str) for item in data["permissions"]):
        raise ValueError("Manifest plugin invalide: permissions doit etre une liste de chaines.")
    unknown_permissions = sorted(set(data["permissions"]) - PERMISSIONS)
    if unknown_permissions:
        raise ValueError(f"Manifest plugin invalide: permissions inconnues {', '.join(unknown_permissions)}.")
    declares = data.get("declares")
    if not isinstance(declares, dict):
        raise ValueError("Manifest plugin invalide: declares doit etre un objet.")
    for key in DECLARATION_KEYS:
        if key not in declares or not isinstance(declares.get(key), list):
            raise ValueError(f"Manifest plugin invalide: declares.{key} doit etre une liste.")


def security_review_for_manifest(data: dict, status: str = "loaded") -> PluginSecurityReview:
    trust_level = str(data.get("trust_level") or "untrusted")
    permissions = [str(item) for item in data.get("permissions") or []]
    warnings: list[str] = []
    critical: list[str] = []
    risk = "low"
    if trust_level == "untrusted":
        warnings.append("Plugin untrusted: disabled par defaut et activation refusee en v0.1.")
        risk = "medium"
    if trust_level == "blocked":
        critical.append("Plugin blocked: jamais activable.")
        risk = "critical"
    if "shell.execute" in permissions:
        critical.append("Permission shell.execute demandee: warning critical, aucun code externe ne sera execute.")
        risk = "critical"
    if any(permission in permissions for permission in {"filesystem.write", "network.access", "browser.control", "desktop.control"}):
        warnings.append("Permission sensible demandee.")
        if risk == "low":
            risk = "high"
    if _manifest_declares_executable_code(data):
        critical.append("Manifest declare du code executable, interdit en v0.1.")
        risk = "critical"
    if status not in {"loaded", "disabled", "enabled"}:
        risk = "critical"
    return PluginSecurityReview(status=status, risk_level=risk, warnings=warnings, critical_warnings=critical, permissions=permissions, trust_level=trust_level)


def enabled_allowed(data: dict, confirmed: bool = False) -> tuple[bool, str]:
    trust_level = str(data.get("trust_level") or "untrusted")
    review = security_review_for_manifest(data)
    if trust_level == "blocked":
        return False, "Plugin blocked jamais activable."
    if review.critical_warnings:
        return False, "Plugin avec warning critical non activable en v0.1."
    if trust_level == "untrusted":
        return False, "Plugin untrusted non activable en v0.1."
    if trust_level == "local" and not confirmed:
        return False, "Plugin local necessite confirmation explicite."
    return True, ""


def _manifest_declares_executable_code(data: dict) -> bool:
    if any(str(key).lower() in EXECUTABLE_MANIFEST_KEYS for key in data):
        return True
    declares = data.get("declares")
    if isinstance(declares, dict):
        if declares.get("hooks"):
            return True
        for values in declares.values():
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict) and any(str(key).lower() in EXECUTABLE_MANIFEST_KEYS for key in item):
                        return True
    return False
