from __future__ import annotations

import os
import subprocess

from omega_agent.compat import function_tool
from omega_agent.config import OmegaConfig
from omega_agent.runtime.project_context import active_config
from omega_agent.security import confirm, log_action, parse_command, workspace_policy_decision


def _shell_env(config: OmegaConfig) -> dict[str, str]:
    env = {
        "HOME": str(config.workspace),
        "USERPROFILE": str(config.workspace),
        "OMEGA_WORKSPACE": str(config.workspace),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _run_shell(config: OmegaConfig, command: str) -> str:
    try:
        args = parse_command(
            command,
            full_access=config.workspace_full_access and config.shell_full_access_in_workspace,
            allow_git_write=config.allow_git_write_in_workspace,
        )
    except Exception as exc:
        log_action(config, "run_shell_denied", {"command": command, "reason": str(exc)})
        return f"Commande refusee: {exc}"

    decision = workspace_policy_decision(config, "run_shell", {"command": command}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "run_shell_denied", {"command": command, "reason": decision.reason, "risk": decision.risk_level})
        return f"Commande refusee: {decision.reason}"

    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Executer dans {config.workspace}: {command}"):
        log_action(config, "run_shell_denied", {"command": command, "reason": "user_denied"})
        return "Commande refusee par l'utilisateur."

    try:
        result = subprocess.run(
            args,
            cwd=config.workspace,
            env=_shell_env(config),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_action(config, "run_shell_timeout", {"command": command})
        return "Commande interrompue: timeout 60s."
    except FileNotFoundError:
        log_action(config, "run_shell_missing_executable", {"command": command, "executable": args[0]})
        return f"Commande introuvable sur cette machine: {args[0]}"

    log_action(config, "run_shell", {"command": command, "returncode": result.returncode})
    output = (result.stdout or "") + (result.stderr or "")
    return output[-12000:] or f"Commande terminee avec code {result.returncode}."


@function_tool
def run_shell(command: str) -> str:
    """Run an allowlisted command inside Omega Agent's workspace."""
    return _run_shell(active_config(), command)
