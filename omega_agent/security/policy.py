from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from omega_agent.config import OmegaConfig
from omega_agent.security.sandbox import safe_path
from omega_agent.security.redaction import redact
from omega_agent.security.risk import score_risk

SENSITIVE_PARTS = {
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".config",
    "keychain",
    "browser",
    "cookies",
}
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "login data",
}
SENSITIVE_NAME_FRAGMENTS = {"token", "secret", "password", "passwd", "credential"}
BLOCKED_COMMANDS = {
    "sudo",
    "su",
    "rm",
    "mkfs",
    "dd",
    "chmod",
    "chown",
    "shutdown",
    "reboot",
    "bcdedit",
    "runas",
    "format",
    "diskpart",
    "taskkill",
    "restart-computer",
    "stop-computer",
}
ALLOWED_COMMANDS = {"pwd", "ls", "dir", "cat", "type", "head", "tail", "pytest", "git"}
ALLOWED_GIT_SUBCOMMANDS = {"status", "diff", "log", "show", "branch"}
FULL_ACCESS_COMMANDS = {
    "pwd",
    "ls",
    "dir",
    "cat",
    "type",
    "head",
    "tail",
    "echo",
    "mkdir",
    "rmdir",
    "del",
    "erase",
    "copy",
    "move",
    "git",
    "npm",
    "node",
    "python",
    "py",
    "pip",
    "pytest",
    "uvicorn",
    "cmd",
    "powershell",
    "pwsh",
}
FULL_ACCESS_GIT_SUBCOMMANDS = {"status", "diff", "log", "show", "branch", "add", "commit", "restore"}
SHELL_METACHARS = set("|&;<>()`")
DENIED_COMMAND_FRAGMENTS = (
    "invoke-webrequest",
    " iwr ",
    " iex",
    "frombase64string",
    "downloadstring",
    "downloadfile",
    "set-executionpolicy",
    "reg add",
    "reg delete",
    "hkey_local_machine",
    "hklm",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "bcdedit",
    "diskpart",
    "rm -rf c:\\",
    "rm -fr c:\\",
    "del /s /q c:\\",
)
WORKSPACE_FULL_ACCESS_TOOLS = {
    "list_files",
    "read_file",
    "write_file",
    "append_file",
    "delete_file",
    "create_directory",
    "delete_directory",
    "move_file",
    "copy_file",
    "list_tree",
    "file_exists",
    "run_shell",
    "git_status",
    "git_diff",
    "git_log",
    "git_branch",
    "git_show",
    "git_add",
    "git_commit",
    "git_restore_file",
}


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str
    risk_level: str = "low"
    redacted_arguments: dict | None = None
    matched_rules: list[dict] | None = None
    warnings: list[str] | None = None
    action_category: str | None = None
    budget_decision: dict | None = None
    shadow_required: bool = False

    @property
    def decision(self) -> str:
        return self.action


def _is_sensitive_name(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in SENSITIVE_PARTS
        or lowered in SENSITIVE_FILE_NAMES
        or any(fragment in lowered for fragment in SENSITIVE_NAME_FRAGMENTS)
    )


def _path_parts(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/")
    return tuple(part for part in PurePosixPath(normalized).parts if part not in {"", "."})


def _validate_shell_arg_scope(arg: str) -> None:
    values = [arg]
    if "=" in arg:
        values.append(arg.split("=", 1)[1])
    for value in values:
        if not value or value.startswith("-"):
            continue
        lowered = value.lower()
        if lowered.startswith(("~", "$home", "${home}", "%userprofile%", "%homepath%")):
            raise PermissionError("Argument hors workspace refuse.")
        if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
            raise PermissionError("Chemin absolu refuse dans une commande shell.")
        parts = _path_parts(value)
        if ".." in parts:
            raise PermissionError("Traversal refuse dans une commande shell.")
        if any(_is_sensitive_name(part) for part in parts):
            raise PermissionError("Chemin sensible refuse dans une commande shell.")


def parse_command(command: str, *, full_access: bool = False, allow_git_write: bool = False) -> list[str]:
    lowered_command = f" {command.lower()} "
    if any(fragment in lowered_command for fragment in DENIED_COMMAND_FRAGMENTS):
        raise PermissionError("Commande PowerShell dangereuse refusee.")
    if "rm -rf /" in lowered_command or "rm -fr /" in lowered_command:
        raise PermissionError("Suppression globale refusee.")
    if any(char in command for char in SHELL_METACHARS):
        raise PermissionError("Metacaractere shell refuse.")
    args = shlex.split(command)
    if not args:
        raise ValueError("Commande vide.")
    executable = Path(args[0]).name
    executable = executable.lower()
    if executable in BLOCKED_COMMANDS:
        raise PermissionError(f"Commande bloquee: {executable}")
    allowed_commands = FULL_ACCESS_COMMANDS if full_access else ALLOWED_COMMANDS
    if executable not in allowed_commands:
        raise PermissionError(f"Commande non autorisee: {executable}")
    if executable == "cmd":
        if not full_access or len(args) < 3 or args[1].lower() != "/c":
            raise PermissionError("cmd autorise seulement au format: cmd /c <commande>.")
        parse_command(" ".join(args[2:]), full_access=full_access, allow_git_write=allow_git_write)
        return args
    for arg in args[1:]:
        _validate_shell_arg_scope(arg)
    if executable == "git":
        allowed_git = FULL_ACCESS_GIT_SUBCOMMANDS if full_access and allow_git_write else ALLOWED_GIT_SUBCOMMANDS
        if len(args) < 2 or args[1] not in allowed_git:
            raise PermissionError("Sous-commande git non autorisee.")
        if any(arg == "-C" or arg.startswith("--git-dir") or arg.startswith("--work-tree") for arg in args[1:]):
            raise PermissionError("Option git hors workspace refusee.")
    if executable in {"powershell", "pwsh"} and any(arg.lower() in {"-encodedcommand", "-ec"} for arg in args[1:]):
        raise PermissionError("PowerShell encoded command refuse.")
    return args


def _base_workspace_policy_decision(config: OmegaConfig, tool_name: str, arguments: dict | None = None, require_approval: bool = True) -> PolicyDecision:
    args = arguments or {}
    try:
        _validate_workspace_tool_request(config, tool_name, args)
    except PermissionError as exc:
        return PolicyDecision("deny", str(exc), "critical", redact(args))
    if config.workspace_full_access and tool_name in WORKSPACE_FULL_ACCESS_TOOLS:
        return PolicyDecision("allow", "Workspace Full Access actif.", "low", redact(args))
    return decide(tool_name, args, require_approval=require_approval)


def workspace_policy_decision(
    config: OmegaConfig,
    tool_name: str,
    arguments: dict | None = None,
    require_approval: bool = True,
    context: dict | None = None,
) -> PolicyDecision:
    args = arguments or {}
    try:
        from omega_agent.security.policy_simulator import PolicySimulator

        payload = {"tool_name": tool_name, "arguments": args, **(context or {})}
        result = PolicySimulator(config).simulate_policy(payload, store=False)
        action = result["final_decision"]
        explicit_approval = any(rule.get("effect") == "require_approval" for rule in (result.get("matched_rules") or []))
        if action == "require_approval" and not require_approval and not explicit_approval:
            action = "allow"
        return PolicyDecision(
            action,
            result.get("reason") or "",
            result.get("risk_level") or "low",
            redact(args),
            matched_rules=result.get("matched_rules") or [],
            warnings=result.get("warnings") or [],
            action_category=result.get("action_category"),
            budget_decision=None,
            shadow_required=bool(result.get("shadow_required")),
        )
    except Exception:
        return _base_workspace_policy_decision(config, tool_name, args, require_approval=require_approval)


def _validate_workspace_tool_request(config: OmegaConfig, tool_name: str, arguments: dict) -> None:
    if tool_name in {"list_files", "read_file", "write_file", "append_file", "delete_file", "create_directory", "delete_directory", "list_tree", "file_exists"}:
        safe_path(config, str(arguments.get("relative_path", ".")))
    elif tool_name in {"move_file", "copy_file"}:
        safe_path(config, str(arguments.get("source_path", "")))
        safe_path(config, str(arguments.get("destination_path", "")))
    elif tool_name == "run_shell":
        cwd = arguments.get("cwd")
        if cwd:
            safe_path(config, str(cwd))
        parse_command(
            str(arguments.get("command", "")),
            full_access=config.workspace_full_access and config.shell_full_access_in_workspace,
            allow_git_write=config.allow_git_write_in_workspace,
        )
    elif tool_name in {"git_status", "git_diff", "git_log", "git_branch", "git_show"}:
        parse_command("git status")
    elif tool_name == "git_add":
        if not config.allow_git_write_in_workspace:
            raise PermissionError("Git write refuse par configuration.")
        safe_path(config, str(arguments.get("relative_path", ".")))
    elif tool_name == "git_commit":
        if not config.allow_git_write_in_workspace:
            raise PermissionError("Git commit refuse par configuration.")
    elif tool_name == "git_restore_file":
        if not config.allow_git_write_in_workspace:
            raise PermissionError("Git restore refuse par configuration.")
        safe_path(config, str(arguments.get("relative_path", "")))


def decide(tool_name: str, arguments: dict | None = None, require_approval: bool = True) -> PolicyDecision:
    assessment = score_risk(tool_name, arguments or {})
    if assessment.level == "critical":
        return PolicyDecision("deny", assessment.reason, assessment.level)
    if require_approval or assessment.level in {"medium", "high"}:
        return PolicyDecision("require_approval", assessment.reason, assessment.level)
    return PolicyDecision("allow", assessment.reason, assessment.level)


def confirm(config: OmegaConfig, message: str) -> bool:
    if not config.require_approval:
        return True
    answer = input(f"\n[Omega approval] {message}\nTaper 'yes' pour autoriser: ").strip().lower()
    return answer == "yes"


def log_action(config: OmegaConfig, action: str, payload: dict) -> None:
    config.ensure_dirs()
    log_file = config.workspace / ".omega" / "actions.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "payload": redact(payload),
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
