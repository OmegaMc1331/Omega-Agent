from __future__ import annotations

from omega_agent.security.policy import SENSITIVE_FILE_NAMES, SENSITIVE_NAME_FRAGMENTS, SENSITIVE_PARTS


def looks_secret(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in SENSITIVE_FILE_NAMES
        or lowered in SENSITIVE_PARTS
        or any(fragment in lowered for fragment in SENSITIVE_NAME_FRAGMENTS)
    )
