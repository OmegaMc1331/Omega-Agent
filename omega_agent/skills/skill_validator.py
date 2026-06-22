from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.runtime.action_journal import classify_action
from omega_agent.runtime.capabilities import CapabilitiesRegistry
from omega_agent.runtime.tools_registry import list_tools
from omega_agent.security.redaction import REDACTED, redact

REQUIRED_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "inputs",
    "steps",
    "required_capabilities",
    "safety_policy",
    "validation",
    "fallback",
    "output_format",
}
DANGEROUS_PATTERNS = (
    r"\brm\s+-rf\b",
    r"\bdel\s+/[sq]\b",
    r"\brmdir\s+/s\b",
    r"\bformat\s+[a-z]:",
    r"\bshutdown\b",
    r"\breg\s+delete\b",
    r"\bchmod\s+777\b",
    r"\bsudo\b",
    r"\brunas\b",
    r"\bgit\s+reset\s+--hard\b",
)
ABSOLUTE_PATH = re.compile(r"(?i)(?:[a-z]:\\|/home/|/root/|/etc/|\\\\[^\\]+\\)")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]

    def as_api(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


class SkillValidator:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def validate(self, definition: dict[str, Any], test_cases: list[dict[str, Any]] | None = None) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(definition, dict):
            return ValidationResult(False, ["Definition must be an object."], [])
        missing = sorted(REQUIRED_FIELDS - set(definition))
        if missing:
            errors.append(f"Missing fields: {', '.join(missing)}")
        text = json.dumps(definition, ensure_ascii=False)
        if redact(definition) != definition or REDACTED in text:
            errors.append("Definition contains a secret or redacted secret marker.")
        if ABSOLUTE_PATH.search(text):
            errors.append("Absolute or sensitive path detected; use workspace-relative paths.")
        lowered = text.lower()
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                errors.append("Dangerous command detected.")
                break
        required = [str(item) for item in definition.get("required_capabilities") or []]
        known = {tool.id for tool in list_tools(self.config)}
        try:
            known.update(cap.id for cap in CapabilitiesRegistry(self.config).list(refresh=True))
        except Exception:
            warnings.append("Capability registry could not be fully refreshed.")
        unknown = [item for item in required if item not in known and f"tool:{item}" not in known]
        if unknown:
            errors.append(f"Unknown capabilities: {', '.join(sorted(set(unknown)))}")
        safety = definition.get("safety_policy") or {}
        if not isinstance(safety, dict) or safety.get("policy_bypass") is not False:
            errors.append("Safety policy must explicitly forbid policy bypass.")
        if safety.get("workspace_only") is not True:
            errors.append("Safety policy must scope writes to the workspace.")
        write_actions = [
            item for item in required
            if item.split(":", 1)[-1] == "run_shell"
            or classify_action(item.split(":", 1)[-1], {}) in {"reversible_write", "destructive_write", "external_side_effect"}
        ]
        if write_actions and not str(definition.get("rollback_notes") or "").strip():
            errors.append("Rollback notes are required for write-capable skills.")
        tests = test_cases or []
        if not tests:
            errors.append("At least one test case is required.")
        return ValidationResult(not errors, errors, warnings)
