from __future__ import annotations

VALID_CAPABILITY_SCOPES = {
    "workspace",
    "filesystem",
    "shell",
    "git",
    "memory",
    "model",
    "provider",
    "session",
    "project",
    "manifest",
    "channel",
    "external",
    "browser",
    "desktop",
}


def normalize_scopes(scopes: list[str] | tuple[str, ...] | None) -> list[str]:
    result = []
    for scope in scopes or []:
        lowered = str(scope).strip().lower()
        if lowered and lowered in VALID_CAPABILITY_SCOPES and lowered not in result:
            result.append(lowered)
    return result
