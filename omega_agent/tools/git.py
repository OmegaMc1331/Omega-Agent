from __future__ import annotations

import shlex

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
    return _run_shell(config, f"git add {shlex.quote(relative_path or '.')}")


def git_commit(config: OmegaConfig, message: str) -> str:
    if not config.allow_git_write_in_workspace:
        return "Git commit refuse: OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE=false."
    if not config.code_allow_git_commit:
        return "Git commit refuse: code.allow_git_commit=false."
    clean_message = " ".join(str(message or "").replace('"', "").replace("'", "").split())[:200]
    if not clean_message:
        return "Git commit refuse: message vide."
    diff = _run_shell(config, "git diff --cached")
    if not diff.strip():
        return "Git commit refuse: aucun changement staged. Lance git_add avant commit."
    return _run_shell(config, f'git commit -m "{clean_message}"')


def git_branch(config: OmegaConfig) -> str:
    return _run_shell(config, "git branch")


def git_show(config: OmegaConfig, ref: str = "HEAD") -> str:
    clean_ref = " ".join(str(ref or "HEAD").split())[:120]
    return _run_shell(config, f"git show {shlex.quote(clean_ref)}")


def git_restore_file(config: OmegaConfig, relative_path: str) -> str:
    if not config.allow_git_write_in_workspace:
        return "Git restore refuse: OMEGA_ALLOW_GIT_WRITE_IN_WORKSPACE=false."
    clean_path = str(relative_path or "").strip()
    if not clean_path:
        return "Git restore refuse: chemin vide."
    return _run_shell(config, f"git restore {shlex.quote(clean_path)}")
