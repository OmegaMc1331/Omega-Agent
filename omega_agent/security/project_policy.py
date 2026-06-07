from __future__ import annotations

import os
import shlex
from dataclasses import replace
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from omega_agent.config import OmegaConfig
from omega_agent.security.policy import SENSITIVE_FILE_NAMES, SENSITIVE_PARTS, _is_sensitive_name, parse_command


FILESYSTEM_TOOLS = {"list_files", "read_file", "write_file", "delete_file", "create_directory", "delete_directory", "move_file", "copy_file", "list_tree"}
SHELL_TOOLS = {"run_shell", "git_status", "git_diff", "git_log", "git_add", "git_commit"}
BROWSER_TOOLS = {
    "browser",
    "browser_stub",
    "browser_open_url",
    "browser_get_title",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "browser_extract_text",
    "browser_close",
}
DESKTOP_TOOLS = {
    "desktop_screenshot",
    "desktop_locate_text_stub",
    "desktop_click",
    "desktop_type",
    "desktop_hotkey",
}
NETWORK_TOOLS = {"web_search", "http_request"}


@dataclass(frozen=True)
class ProjectPolicy:
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    shell_allowlist: list[str] = field(default_factory=list)
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    require_approval_for_write: bool = True
    require_approval_for_shell: bool = True
    network_allowed: bool = False
    browser_allowed: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> "ProjectPolicy":
        payload = data or {}
        return cls(
            allowed_tools=_string_list(payload.get("allowed_tools")),
            denied_tools=_string_list(payload.get("denied_tools")),
            shell_allowlist=_string_list(payload.get("shell_allowlist")),
            read_paths=_string_list(payload.get("read_paths")),
            write_paths=_string_list(payload.get("write_paths")),
            require_approval_for_write=bool(payload.get("require_approval_for_write", True)),
            require_approval_for_shell=bool(payload.get("require_approval_for_shell", True)),
            network_allowed=bool(payload.get("network_allowed", False)),
            browser_allowed=bool(payload.get("browser_allowed", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def default_project_policy(config: OmegaConfig) -> ProjectPolicy:
    return ProjectPolicy(
        read_paths=["."],
        write_paths=["."],
        require_approval_for_write=config.require_approval,
        require_approval_for_shell=config.require_approval,
    )


def validate_project_root(root_path: str | Path) -> Path:
    root = Path(root_path).expanduser().resolve()
    home = Path.home().resolve()
    if root == home:
        raise PermissionError("Le root_path d'un projet ne peut pas etre HOME.")
    if root.parent == root:
        raise PermissionError("Le root_path d'un projet ne peut pas etre la racine du systeme de fichiers.")
    if any(_is_sensitive_root_part(part) for part in root.parts):
        raise PermissionError("Le root_path d'un projet ne peut pas pointer vers un emplacement sensible.")
    return root


def safe_project_path(root_path: str | Path, relative_path: str, policy: ProjectPolicy | None = None, mode: str = "read") -> Path:
    root = validate_project_root(root_path)
    raw_path = (relative_path or ".").strip()
    if raw_path in {".", "./"}:
        target = root
    else:
        if raw_path.startswith("~") or PureWindowsPath(raw_path).is_absolute() or PurePosixPath(raw_path).is_absolute():
            raise PermissionError("Acces refuse: le chemin doit etre relatif au projet.")
        target = (root / raw_path).resolve()

    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise PermissionError("Acces refuse: chemin hors projet.")
    relative_parts = target.relative_to(root).parts
    if any(_is_sensitive_name(part) for part in relative_parts):
        raise PermissionError("Acces refuse: chemin sensible.")

    active_policy = policy or ProjectPolicy()
    allowed = active_policy.write_paths if mode == "write" else active_policy.read_paths
    if not allowed:
        allowed = ["."]
    allowed_roots = [_policy_path(root, item) for item in allowed]
    if not any(os.path.commonpath([str(allowed_root), str(target)]) == str(allowed_root) for allowed_root in allowed_roots):
        raise PermissionError(f"Acces {mode} refuse par la politique projet.")
    return target


def project_config(config: OmegaConfig, root_path: str | Path, policy: ProjectPolicy | None = None, tool_id: str | None = None) -> OmegaConfig:
    active_policy = policy or ProjectPolicy()
    require_approval = config.require_approval
    if config.workspace_full_access and tool_id in FILESYSTEM_TOOLS | SHELL_TOOLS:
        require_approval = False
    if tool_id in {"write_file", "delete_file", "create_directory", "delete_directory", "move_file", "copy_file"}:
        require_approval = require_approval or active_policy.require_approval_for_write
    if tool_id in SHELL_TOOLS:
        require_approval = require_approval or active_policy.require_approval_for_shell
    if config.workspace_full_access and tool_id in FILESYSTEM_TOOLS | SHELL_TOOLS:
        require_approval = False
    return replace(config, workspace=validate_project_root(root_path), require_approval=require_approval)


def validate_project_tool(tool_id: str, arguments: dict, root_path: str | Path, policy: ProjectPolicy, config: OmegaConfig | None = None) -> None:
    if tool_id in policy.denied_tools:
        raise PermissionError(f"Tool refuse par le projet: {tool_id}")
    if policy.allowed_tools and tool_id not in policy.allowed_tools:
        raise PermissionError(f"Tool non autorise par le projet: {tool_id}")
    if tool_id in NETWORK_TOOLS and not policy.network_allowed:
        raise PermissionError("Acces reseau refuse par la politique projet.")
    if tool_id in BROWSER_TOOLS and not policy.browser_allowed:
        raise PermissionError("Acces navigateur refuse par la politique projet.")
    if tool_id in {"list_files", "read_file", "list_tree"}:
        safe_project_path(root_path, str(arguments.get("relative_path", ".")), policy, mode="read")
    if tool_id in {"write_file", "delete_file", "create_directory", "delete_directory"}:
        safe_project_path(root_path, str(arguments.get("relative_path", "")), policy, mode="write")
    if tool_id in {"move_file", "copy_file"}:
        safe_project_path(root_path, str(arguments.get("source_path", "")), policy, mode="read")
        safe_project_path(root_path, str(arguments.get("destination_path", "")), policy, mode="write")
    if tool_id == "run_shell":
        args = parse_command(
            str(arguments.get("command", "")),
            full_access=bool(config and config.workspace_full_access and config.shell_full_access_in_workspace),
            allow_git_write=bool(config and config.allow_git_write_in_workspace),
        )
        if policy.shell_allowlist:
            executable = Path(args[0]).name
            if executable not in set(policy.shell_allowlist):
                raise PermissionError(f"Commande non autorisee par le projet: {executable}")
    if tool_id.startswith("git_"):
        if policy.shell_allowlist and "git" not in set(policy.shell_allowlist):
            raise PermissionError("Commande git non autorisee par le projet.")


def _policy_path(root: Path, value: str) -> Path:
    raw = (value or ".").strip()
    if raw.startswith("~"):
        raise PermissionError("Chemin de policy hors projet refuse.")
    if PureWindowsPath(raw).is_absolute() or PurePosixPath(raw).is_absolute():
        target = Path(raw).resolve()
    else:
        target = (root / raw).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise PermissionError("Chemin de policy hors projet refuse.")
    relative_parts = target.relative_to(root).parts
    if any(_is_sensitive_name(part) for part in relative_parts):
        raise PermissionError("Chemin sensible refuse dans la policy projet.")
    return target


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in shlex.split(value) if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _is_sensitive_root_part(value: str) -> bool:
    lowered = value.lower()
    return lowered in SENSITIVE_PARTS or lowered in SENSITIVE_FILE_NAMES or lowered in {"tokens", "secrets", "passwords", "credentials", "cookies", "keychain"}
