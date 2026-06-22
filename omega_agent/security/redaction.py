from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

SECRET_KEY_FRAGMENTS = {
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "cookie",
    "credential",
    "id_rsa",
    "id_ed25519",
    "password",
    "passwd",
    "secret",
    "token",
}

SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(token=)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(password=)[^\s&]+"),
    re.compile(r"(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?:~|/home/[^/\s]+|C:\\Users\\[^\\\s]+)[/\\]\.ssh[/\\][^\s]+"),
    re.compile(r"(?i)(?:~|/home/[^/\s]+|C:\\Users\\[^\\\s]+)[/\\](?:\.codex|\.config[/\\]codex|\.omega[/\\]auth)[^\s]*"),
    re.compile(r"(?i)(?:^|\s)(?:[A-Za-z]:\\[^\s]*(?:\.ssh|cookies|Login Data|Local State|\.env)[^\s]*)"),
)

REDACTED = "[REDACTED]"
NON_SECRET_OPERATIONAL_KEYS = {
    "estimated_tokens",
    "max_estimated_tokens",
    "token_count",
    "tokens_used",
}


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in NON_SECRET_OPERATIONAL_KEYS:
        return False
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
        else:
            redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact(value):
    if isinstance(value, Mapping):
        return {str(key): REDACTED if is_sensitive_key(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact(item) for item in value]
    return value
