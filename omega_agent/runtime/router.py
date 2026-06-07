from __future__ import annotations

from omega_agent.runtime.agent_profiles import DEFAULT_AGENT_PROFILE_ID

CODER_KEYWORDS = {"code", "repo", "repository", "tests", "test", "bug", "pytest", "developpement", "développement"}
SECURITY_KEYWORDS = {"audit", "securite", "sécurité", "vulnerabilite", "vulnérabilité", "vulnerability", "secret", "cve"}
OPERATOR_KEYWORDS = {"automatiser", "automate", "ouvrir", "cliquer", "click", "desktop", "browser"}


def choose_agent_profile(message: str, current_profile_id: str | None = None, manual: bool = False) -> str:
    if manual and current_profile_id:
        return current_profile_id
    if current_profile_id and current_profile_id != DEFAULT_AGENT_PROFILE_ID:
        return current_profile_id

    lowered = message.lower()
    words = set(lowered.replace(",", " ").replace(".", " ").split())
    if words.intersection(CODER_KEYWORDS):
        return "omega-coder"
    if words.intersection(SECURITY_KEYWORDS):
        return "omega-security"
    if words.intersection(OPERATOR_KEYWORDS):
        return "omega-operator"
    return DEFAULT_AGENT_PROFILE_ID
