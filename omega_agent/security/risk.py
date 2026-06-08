from __future__ import annotations

from dataclasses import dataclass

SENSITIVE_TERMS = {"token", "secret", "password", "credential", ".ssh", "cookies", "login data", "id_rsa"}
NETWORK_TERMS = {"http://", "https://", "invoke-webrequest", "curl", "wget", "iex"}
WRITE_TERMS = {"write", "delete", "remove", "rm", "del", "erase", "move", "copy", ">"}


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    score: int
    reason: str


def score_risk(tool_name: str, arguments: dict | None = None) -> RiskAssessment:
    args = arguments or {}
    haystack = f"{tool_name} {args}".lower()
    score = 5
    reasons: list[str] = []

    if tool_name in {"write_file", "append_file", "delete_file", "delete_directory", "move_file", "copy_file", "run_shell", "git_add", "git_commit", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}:
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
