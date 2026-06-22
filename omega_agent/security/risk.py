from __future__ import annotations

from dataclasses import dataclass

SENSITIVE_TERMS = {"token", "secret", "password", "credential", ".ssh", "cookies", "login data", "id_rsa"}
NETWORK_TERMS = {"http://", "https://", "invoke-webrequest", "curl", "wget", "iex"}
WRITE_TERMS = {"write", "delete", "remove", "rm", "del", "erase", "move", "copy", ">"}
RISK_LEVEL_SCORES = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    score: int
    reason: str


def risk_level_score(level: str) -> int:
    return RISK_LEVEL_SCORES.get(str(level or "low").lower(), 1)


def max_risk_level(*levels: str) -> str:
    return max((str(level or "low").lower() for level in levels), key=risk_level_score, default="low")


def score_risk(tool_name: str, arguments: dict | None = None) -> RiskAssessment:
    args = arguments or {}
    haystack = f"{tool_name} {args}".lower()
    score = 5
    reasons: list[str] = []

    if tool_name == "invoke_connector_operation":
        category = str(args.get("action_category") or "").lower()
        if category == "system_sensitive":
            score += 90
            reasons.append("operation connecteur system-sensitive")
        elif category == "external_side_effect":
            score += 60
            reasons.append("operation connecteur externe")
        elif category == "destructive_write":
            score += 55
            reasons.append("operation connecteur destructive")
        elif category == "reversible_write":
            score += 35
            reasons.append("operation connecteur en ecriture")
        else:
            score += 10
            reasons.append("operation connecteur lecture")
    if tool_name in {"write_file", "append_file", "delete_file", "delete_directory", "move_file", "copy_file", "run_shell", "git_add", "git_commit", "git_restore_file", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}:
        score += 45
        reasons.append("action sensible")
    if tool_name.startswith("browser_"):
        score += 15
        reasons.append("automation navigateur")
    if tool_name.startswith("desktop_"):
        score += 20
        reasons.append("automation desktop")
    if any(term in haystack for term in SENSITIVE_TERMS):
        score += 55
        reasons.append("reference a un secret ou chemin sensible")
    if any(term in haystack for term in NETWORK_TERMS):
        score += 25
        reasons.append("destination reseau ou execution distante")
    if any(term in haystack for term in WRITE_TERMS):
        score += 20
        reasons.append("ecriture ou suppression potentielle")
    if ".." in haystack or "~/" in haystack or "~\\" in haystack:
        score += 30
        reasons.append("chemin hors perimetre possible")

    if score >= 90:
        level = "critical"
    elif score >= 55:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"
    return RiskAssessment(level=level, score=score, reason=", ".join(reasons) or "risque faible")
