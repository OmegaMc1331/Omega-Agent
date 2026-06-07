from __future__ import annotations

import os

from omega_agent.config_store import expected_secret_status
from omega_agent.security.policy import SENSITIVE_FILE_NAMES, SENSITIVE_NAME_FRAGMENTS, SENSITIVE_PARTS


def looks_secret(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in SENSITIVE_FILE_NAMES
        or lowered in SENSITIVE_PARTS
        or any(fragment in lowered for fragment in SENSITIVE_NAME_FRAGMENTS)
    )


def secret_configured(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def secrets_status() -> list[dict]:
    return expected_secret_status()
