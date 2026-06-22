from __future__ import annotations

import os

from omega_agent.security.redaction import redact, redact_text


def auth_ref_status(auth_ref: str | None) -> str:
    if not auth_ref:
        return "none"
    return "configured" if os.getenv(str(auth_ref), "").strip() else "missing"


def redact_auth_ref(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_text(value)


def redacted_secret_payload(payload):
    return redact(payload)
