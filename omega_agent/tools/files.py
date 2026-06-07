from __future__ import annotations

import shutil

from omega_agent.compat import function_tool
from omega_agent.config import OmegaConfig
from omega_agent.runtime.project_context import active_config
from omega_agent.security import confirm, log_action, safe_path, workspace_policy_decision


def _list_files(config: OmegaConfig, relative_path: str) -> str:
    path = safe_path(config, relative_path)
    if not path.exists():
        log_action(config, "list_files", {"path": relative_path, "exists": False})
        return f"Chemin introuvable: {relative_path}"
    if path.is_file():
        log_action(config, "list_files", {"path": relative_path, "kind": "file"})
        return path.name
    items = []
    for child in sorted(path.iterdir()):
        suffix = "/" if child.is_dir() else ""
        items.append(child.name + suffix)
    log_action(config, "list_files", {"path": relative_path, "kind": "directory"})
    return "\n".join(items) or "Dossier vide."


def _read_file(config: OmegaConfig, relative_path: str) -> str:
    path = safe_path(config, relative_path)
    if not path.exists() or not path.is_file():
        return f"Fichier introuvable: {relative_path}"
    content = path.read_text(encoding="utf-8", errors="replace")
    log_action(config, "read_file", {"path": relative_path})
    return content[:12000]


def _write_file(config: OmegaConfig, relative_path: str, content: str) -> str:
    path = safe_path(config, relative_path)
    decision = workspace_policy_decision(config, "write_file", {"relative_path": relative_path, "content": content[:256]}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "write_file_denied", {"path": relative_path, "reason": decision.reason, "risk": decision.risk_level})
        return f"Ecriture refusee: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Ecrire le fichier {path} ?"):
        log_action(config, "write_file_denied", {"path": relative_path})
        return "Ecriture refusee par l'utilisateur."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    log_action(config, "write_file", {"path": relative_path, "bytes": len(content.encode("utf-8"))})
    return f"Fichier ecrit: {relative_path}"


def _delete_file(config: OmegaConfig, relative_path: str) -> str:
    path = safe_path(config, relative_path)
    if not config.allow_delete_in_workspace:
        return "Suppression refusee: OMEGA_ALLOW_DELETE_IN_WORKSPACE=false."
    decision = workspace_policy_decision(config, "delete_file", {"relative_path": relative_path}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "delete_file_denied", {"path": relative_path, "reason": decision.reason, "risk": decision.risk_level})
        return f"Suppression refusee: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Supprimer le fichier {path} ?"):
        log_action(config, "delete_file_denied", {"path": relative_path, "reason": "user_denied"})
        return "Suppression refusee par l'utilisateur."
    if not path.exists() or not path.is_file():
        return f"Fichier introuvable: {relative_path}"
    path.unlink()
    log_action(config, "delete_file", {"path": relative_path})
    return f"Fichier supprime: {relative_path}"


def _create_directory(config: OmegaConfig, relative_path: str) -> str:
    path = safe_path(config, relative_path)
    decision = workspace_policy_decision(config, "create_directory", {"relative_path": relative_path}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "create_directory_denied", {"path": relative_path, "reason": decision.reason})
        return f"Creation dossier refusee: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Creer le dossier {path} ?"):
        return "Creation dossier refusee par l'utilisateur."
    path.mkdir(parents=True, exist_ok=True)
    log_action(config, "create_directory", {"path": relative_path})
    return f"Dossier cree: {relative_path}"


def _delete_directory(config: OmegaConfig, relative_path: str) -> str:
    path = safe_path(config, relative_path)
    if not config.allow_delete_in_workspace:
        return "Suppression refusee: OMEGA_ALLOW_DELETE_IN_WORKSPACE=false."
    decision = workspace_policy_decision(config, "delete_directory", {"relative_path": relative_path}, require_approval=config.require_approval)
    if decision.action == "deny":
        log_action(config, "delete_directory_denied", {"path": relative_path, "reason": decision.reason})
        return f"Suppression dossier refusee: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Supprimer le dossier {path} ?"):
        return "Suppression dossier refusee par l'utilisateur."
    if path == config.workspace.resolve():
        return "Suppression refusee: racine workspace."
    if not path.exists() or not path.is_dir():
        return f"Dossier introuvable: {relative_path}"
    shutil.rmtree(path)
    log_action(config, "delete_directory", {"path": relative_path})
    return f"Dossier supprime: {relative_path}"


def _move_file(config: OmegaConfig, source_path: str, destination_path: str) -> str:
    source = safe_path(config, source_path)
    destination = safe_path(config, destination_path)
    decision = workspace_policy_decision(config, "move_file", {"source_path": source_path, "destination_path": destination_path}, require_approval=config.require_approval)
    if decision.action == "deny":
        return f"Deplacement refuse: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Deplacer {source} vers {destination} ?"):
        return "Deplacement refuse par l'utilisateur."
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    log_action(config, "move_file", {"source": source_path, "destination": destination_path})
    return f"Fichier deplace: {source_path} -> {destination_path}"


def _copy_file(config: OmegaConfig, source_path: str, destination_path: str) -> str:
    source = safe_path(config, source_path)
    destination = safe_path(config, destination_path)
    decision = workspace_policy_decision(config, "copy_file", {"source_path": source_path, "destination_path": destination_path}, require_approval=config.require_approval)
    if decision.action == "deny":
        return f"Copie refusee: {decision.reason}"
    if decision.action == "require_approval" and config.require_approval and not confirm(config, f"Copier {source} vers {destination} ?"):
        return "Copie refusee par l'utilisateur."
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    log_action(config, "copy_file", {"source": source_path, "destination": destination_path})
    return f"Fichier copie: {source_path} -> {destination_path}"


def _list_tree(config: OmegaConfig, relative_path: str = ".", max_entries: int = 200) -> str:
    root = safe_path(config, relative_path)
    if not root.exists():
        return f"Chemin introuvable: {relative_path}"
    entries: list[str] = []
    for child in sorted(root.rglob("*")):
        if len(entries) >= max_entries:
            entries.append("...")
            break
        try:
            safe_path(config, str(child.resolve().relative_to(config.workspace.resolve())))
        except Exception:
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(str(child.relative_to(root)).replace("\\", "/") + suffix)
    log_action(config, "list_tree", {"path": relative_path, "entries": len(entries)})
    return "\n".join(entries) or "Dossier vide."


@function_tool
def list_files(relative_path: str) -> str:
    """List files inside Omega Agent's workspace."""
    return _list_files(active_config(), relative_path)


@function_tool
def read_file(relative_path: str) -> str:
    """Read a UTF-8 text file inside Omega Agent's workspace."""
    return _read_file(active_config(), relative_path)


@function_tool
def write_file(relative_path: str, content: str) -> str:
    """Write a UTF-8 text file inside Omega Agent's workspace."""
    return _write_file(active_config(), relative_path, content)


@function_tool
def delete_file(relative_path: str) -> str:
    """Delete a file inside Omega Agent's workspace when policy allows it."""
    return _delete_file(active_config(), relative_path)


@function_tool
def create_directory(relative_path: str) -> str:
    """Create a directory inside Omega Agent's workspace."""
    return _create_directory(active_config(), relative_path)


@function_tool
def delete_directory(relative_path: str) -> str:
    """Delete a directory inside Omega Agent's workspace when policy allows it."""
    return _delete_directory(active_config(), relative_path)


@function_tool
def move_file(source_path: str, destination_path: str) -> str:
    """Move a file inside Omega Agent's workspace."""
    return _move_file(active_config(), source_path, destination_path)


@function_tool
def copy_file(source_path: str, destination_path: str) -> str:
    """Copy a file inside Omega Agent's workspace."""
    return _copy_file(active_config(), source_path, destination_path)


@function_tool
def list_tree(relative_path: str = ".", max_entries: int = 200) -> str:
    """List a tree inside Omega Agent's workspace."""
    return _list_tree(active_config(), relative_path, max_entries)
