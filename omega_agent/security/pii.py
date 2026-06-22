from __future__ import annotations

import re

from omega_agent.security.redaction import REDACTED, redact_text

SENSITIVE_MEMORY_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile(r"\bapi[_ -]?key\b", re.IGNORECASE),
    re.compile(r"\btoken\b", re.IGNORECASE),
    re.compile(r"\bpassword\b", re.IGNORECASE),
    re.compile(r"\bauthorization\b", re.IGNORECASE),
    re.compile(r"private key", re.IGNORECASE),
    re.compile(r"(?:^|[\\/])\.ssh(?:[\\/]|$)", re.IGNORECASE),
)


def redact_memory_text(value: str) -> str:
    return redact_text(value or "")


def contains_sensitive(value: str) -> bool:
    text = value or ""
    if REDACTED in text:
        return False
    return any(pattern.search(text) for pattern in SENSITIVE_MEMORY_PATTERNS)
