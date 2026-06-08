from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from omega_agent.config import OmegaConfig

SENSITIVE_PATH_PARTS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    "cookies",
    "keychain",
    "login data",
    "chrome",
    "edge",
    "firefox",
    "mozilla",
}
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "cookies",
    "login data",
}
SENSITIVE_NAME_FRAGMENTS = {"token", "secret", "password", "passwd", "credential"}


def resolve_workspace_path(path: str | Path, workspace: str | Path) -> Path:
    raw = str(path or ".").strip()
    root = Path(workspace).expanduser().resolve()
    if raw in {"", ".", "./"}:
        candidate = root
    elif raw.startswith("~"):
        candidate = Path(raw).expanduser().resolve()
    elif PureWindowsPath(raw).is_absolute() or PurePosixPath(raw).is_absolute():
        candidate = Path(raw).expanduser().resolve()
    else:
        if ".." in _path_parts(raw):
            raise PermissionError("Traversal refuse.")
        candidate = (root / raw).resolve()
    return candidate


def is_path_inside_workspace(path: str | Path, workspace: str | Path) -> bool:
    root = Path(workspace).expanduser().resolve()
    candidate = Path(path).expanduser().resolve()
    try:
        return os.path.commonpath([str(root), str(candidate)]) == str(root)
    except ValueError:
        return False


def assert_inside_workspace(path: str | Path, workspace: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    root = Path(workspace).expanduser().resolve()
    if not is_path_inside_workspace(candidate, root):
        raise PermissionError("Acces refuse: chemin hors workspace.")
    if is_sensitive_path(candidate):
        raise PermissionError("Acces refuse: chemin sensible.")
    if is_symlink_escape(candidate, root):
        raise PermissionError("Acces refuse: symlink hors workspace.")
    return candidate


def is_sensitive_path(path: str | Path) -> bool:
    candidate = Path(path)
    for part in candidate.parts:
        lowered = part.lower()
        if (
            lowered in SENSITIVE_PATH_PARTS
            or lowered in SENSITIVE_FILE_NAMES
            or any(fragment in lowered for fragment in SENSITIVE_NAME_FRAGMENTS)
        ):
            return True
    return False


def is_symlink_escape(path: str | Path, workspace: str | Path) -> bool:
    root = Path(workspace).expanduser().resolve()
    candidate = Path(path)
    current = candidate if candidate.exists() else candidate.parent
    while True:
        if current.exists() and current.is_symlink():
            try:
                if not is_path_inside_workspace(current.resolve(), root):
                    return True
            except OSError:
                return True
        if current == root or current.parent == current:
            return False
        current = current.parent


def safe_path(config: OmegaConfig, relative_path: str) -> Path:
    target = resolve_workspace_path(relative_path, config.workspace)
    return assert_inside_workspace(target, config.workspace)


def _path_parts(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/")
    return tuple(part for part in PurePosixPath(normalized).parts if part not in {"", "."})


__all__ = [
    "OmegaConfig",
    "resolve_workspace_path",
    "is_path_inside_workspace",
    "assert_inside_workspace",
    "is_sensitive_path",
    "is_symlink_escape",
    "safe_path",
]
