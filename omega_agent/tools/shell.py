from __future__ import annotations

import json
import os
import subprocess

from omega_agent.compat import function_tool
from omega_agent.config import OmegaConfig
from omega_agent.runtime.project_context import active_config
from omega_agent.security import confirm, log_action, parse_command, safe_path, workspace_policy_decision


def _shell_env(config: OmegaConfig) -> dict[str, str]:
    env = {
        "HOME": str(config.workspace),
        "USERPROFILE": str(config.workspace),
        "OMEGA_WORKSPACE": str(config.workspace),
        "GIT_CEILING_DIRECTORIES": str(config.workspace.parent),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _run_shell(config: OmegaConfig, command: str, cwd: str | None = None, timeout_seconds: int = 60) -> str:
    workdir = safe_path(config, cwd or ".")
    if not workdir.exists() or not workdir.is_dir():
        return f"Commande refusee: cwd introuvable ou non dossier: {cwd or '.'}"
    try:
        args = parse_command(
            command,
            full_access=config.workspace_full_access and config.shell_full_access_in_workspace,
            allow_git_write=config.allow_git_write_in_workspace,
        )
    except Exception as exc:
        log_action(config, "run_shell_denied", {"command": command, "reason": str(exc)})
        return f"Commande refusee: {exc}"

    decision = workspace_policy_decision(config, "run_shell", {"command": command, "cwd": cwd or "."}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "run_shell_denied", {"command": command, "reason": decision.reason, "risk": decision.risk_level})
        return f"Commande refusee: {decision.reason}"

    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Executer dans {workdir}: {command}"):
        log_action(config, "run_shell_denied", {"command": command, "reason": "user_denied"})
        return "Commande refusee par l'utilisateur."

    try:
        result = subprocess.run(
            args,
            cwd=workdir,
            env=_shell_env(config),
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout_seconds or 60), 300)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_action(config, "run_shell_timeout", {"command": command})
        return "Commande interrompue: timeout 60s."
    except FileNotFoundError:
        log_action(config, "run_shell_missing_executable", {"command": command, "executable": args[0]})
        return f"Commande introuvable sur cette machine: {args[0]}"

    log_action(config, "run_shell", {"command": command, "returncode": result.returncode})
    stdout = (result.stdout or "")[-10000:]
    stderr = (result.stderr or "")[-4000:]
    if stdout and not stderr and result.returncode == 0:
        return stdout
    return json.dumps({"exit_code": result.returncode, "stdout": stdout, "stderr": stderr}, ensure_ascii=False)


@function_tool
def run_shell(command: str) -> str:
    """Run an allowlisted command inside Omega Agent's workspace."""
    return _run_shell(active_config(), command)
