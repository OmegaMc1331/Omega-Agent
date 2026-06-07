from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.tools.shell import _run_shell


def git_status(config: OmegaConfig) -> str:
    return _run_shell(config, "git status")


def git_diff(config: OmegaConfig) -> str:
    return _run_shell(config, "git diff")


def git_log(config: OmegaConfig) -> str:
    return _run_shell(config, "git log")


def git_add(config: OmegaConfig, relative_path: str = ".") -> str:
    if not config.allow_git_write_in_workspace:
        return "Git add refuse: OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE=false."
    return _run_shell(config, f"git add {relative_path}")


def git_commit(config: OmegaConfig, message: str) -> str:
    if not config.allow_git_write_in_workspace:
        return "Git commit refuse: OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE=false."
    clean_message = " ".join(str(message or "").replace('"', "").replace("'", "").split())[:200]
    if not clean_message:
        return "Git commit refuse: message vide."
    return _run_shell(config, f'git commit -m "{clean_message}"')
