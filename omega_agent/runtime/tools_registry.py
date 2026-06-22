from __future__ import annotations

from dataclasses import dataclass, field

from omega_agent.config import OmegaConfig
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.tools.browser import _browser_click, _browser_close, _browser_extract_text, _browser_get_title, _browser_open_url, _browser_screenshot, _browser_type
from omega_agent.tools.desktop import _desktop_click, _desktop_hotkey, _desktop_locate_text_stub, _desktop_screenshot, _desktop_type
from omega_agent.tools.files import _append_file, _copy_file, _create_directory, _delete_directory, _delete_file, _file_exists, _list_files, _list_tree, _move_file, _read_file, _write_file
from omega_agent.tools.git import git_add, git_branch, git_commit, git_diff, git_log, git_restore_file, git_show, git_status
from omega_agent.tools.memory import _recall, _remember
from omega_agent.tools.shell import _run_shell
from omega_agent.tools.system import system_info


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    description: str
    input_schema: dict
    category: str
    risk: str
    enabled: bool
    requires_approval: bool
    output_schema: dict | None = None
    risk_level: str = ""
    handler: str = ""

    def __post_init__(self):
        if not self.risk_level:
            object.__setattr__(self, "risk_level", self.risk)
        if not self.handler:
            object.__setattr__(self, "handler", self.id)


def list_tools(config: OmegaConfig | None = None) -> list[ToolDefinition]:
    full_access = bool(config and config.workspace_full_access)
    write_approval = not full_access
    shell_approval = not (full_access and config and config.shell_full_access_in_workspace)
    delete_enabled = bool(config and config.allow_delete_in_workspace)
    git_write_enabled = bool(config and config.allow_git_write_in_workspace)
    tools = [
        ToolDefinition("list_files", "List files", "Liste les fichiers dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "low", True, False),
        ToolDefinition("read_file", "Read file", "Lit un fichier texte non sensible dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "medium", True, False),
        ToolDefinition("write_file", "Write file", "Ecrit un fichier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}, "content": {"type": "string"}}}, "filesystem", "high", True, write_approval),
        ToolDefinition("append_file", "Append file", "Ajoute du texte dans un fichier de OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}, "content": {"type": "string"}}}, "filesystem", "high", True, write_approval),
        ToolDefinition("delete_file", "Delete file", "Supprime un fichier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "high", delete_enabled, write_approval),
        ToolDefinition("create_directory", "Create directory", "Cree un dossier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "medium", True, write_approval),
        ToolDefinition("delete_directory", "Delete directory", "Supprime un dossier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "high", delete_enabled, write_approval),
        ToolDefinition("move_file", "Move file", "Deplace un fichier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"source_path": {"type": "string"}, "destination_path": {"type": "string"}}}, "filesystem", "high", True, write_approval),
        ToolDefinition("copy_file", "Copy file", "Copie un fichier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"source_path": {"type": "string"}, "destination_path": {"type": "string"}}}, "filesystem", "medium", True, write_approval),
        ToolDefinition("list_tree", "List tree", "Liste recursivement un dossier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}, "max_entries": {"type": "integer"}}}, "filesystem", "low", True, False),
        ToolDefinition("file_exists", "File exists", "Verifie l'existence d'un fichier dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "filesystem", "low", True, False),
        ToolDefinition("run_shell", "Run shell", "Execute une commande allowlistee dans OMEGA_WORKSPACE.", {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout_seconds": {"type": "integer"}}}, "shell", "high", True, shell_approval),
        ToolDefinition("remember", "Remember", "Ajoute une memoire locale SQLite.", {"type": "object", "properties": {"content": {"type": "string"}, "tags": {"type": "string"}}}, "memory", "low", True, False),
        ToolDefinition("recall", "Recall", "Recherche dans la memoire locale.", {"type": "object", "properties": {"query": {"type": "string"}}}, "memory", "low", True, False),
        ToolDefinition("search_memory", "Search memory", "Alias de recherche memoire.", {"type": "object", "properties": {"query": {"type": "string"}}}, "memory", "low", True, False),
        ToolDefinition("git_status", "Git status", "Affiche le statut git du workspace.", {"type": "object", "properties": {}}, "git", "low", True, False),
        ToolDefinition("git_diff", "Git diff", "Affiche le diff git du workspace.", {"type": "object", "properties": {}}, "git", "medium", True, False),
        ToolDefinition("git_log", "Git log", "Affiche l'historique git recent.", {"type": "object", "properties": {}}, "git", "low", True, False),
        ToolDefinition("git_branch", "Git branch", "Affiche les branches git locales.", {"type": "object", "properties": {}}, "git", "low", True, False),
        ToolDefinition("git_show", "Git show", "Affiche un objet git sans ecriture.", {"type": "object", "properties": {"ref": {"type": "string"}}}, "git", "medium", True, False),
        ToolDefinition("git_add", "Git add", "Ajoute des fichiers git dans le workspace.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "git", "high", git_write_enabled, write_approval),
        ToolDefinition("git_commit", "Git commit", "Cree un commit git dans le workspace.", {"type": "object", "properties": {"message": {"type": "string"}}}, "git", "high", git_write_enabled, write_approval),
        ToolDefinition("git_restore_file", "Git restore file", "Restaure un fichier versionne depuis git dans le workspace.", {"type": "object", "properties": {"relative_path": {"type": "string"}}}, "git", "high", git_write_enabled, write_approval),
        ToolDefinition("system_info", "System info", "Affiche les informations systeme non sensibles.", {"type": "object", "properties": {}}, "system", "low", True, False),
        ToolDefinition("delegate_to_agent", "Delegate to agent", "Delegue une sous-tache a un profil agent enfant sans escalade de permissions.", {"type": "object", "properties": {"child_agent_id": {"type": "string"}, "task": {"type": "string"}, "max_steps": {"type": "integer"}, "allowed_tools": {"type": "array", "items": {"type": "string"}}}}, "agent", "medium", True, False),
        ToolDefinition(
            "invoke_connector_operation",
            "Invoke connector operation",
            "Appelle une operation de connecteur API-first activee et gouvernee par policy.",
            {
                "type": "object",
                "properties": {
                    "connector_id": {"type": "string"},
                    "operation_id": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["connector_id", "operation_id"],
            },
            "connector",
            "high",
            bool(config.connectors_enabled) if config is not None else True,
            False,
        ),
    ]
    if config is not None and config.browser_enabled:
        tools.extend(
            [
                ToolDefinition("browser_open_url", "Browser open URL", "Ouvre une URL HTTP(S) dans un profil navigateur Omega isole.", {"type": "object", "properties": {"url": {"type": "string"}}}, "browser", "medium", True, False),
                ToolDefinition("browser_get_title", "Browser get title", "Retourne le titre de la page active.", {"type": "object", "properties": {}}, "browser", "low", True, False),
                ToolDefinition("browser_screenshot", "Browser screenshot", "Capture un screenshot marque untrusted dans le workspace.", {"type": "object", "properties": {"full_page": {"type": "boolean"}}}, "browser", "medium", True, False),
                ToolDefinition("browser_click", "Browser click", "Clique un selector Playwright apres approval.", {"type": "object", "properties": {"selector": {"type": "string"}, "label": {"type": "string"}}}, "browser", "high", True, True),
                ToolDefinition("browser_type", "Browser type", "Remplit un champ via selector Playwright apres approval.", {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}}, "browser", "high", True, True),
                ToolDefinition("browser_extract_text", "Browser extract text", "Extrait du texte de la page active et le marque untrusted.", {"type": "object", "properties": {"selector": {"type": "string"}, "limit": {"type": "integer"}}}, "browser", "medium", True, False),
                ToolDefinition("browser_close", "Browser close", "Ferme le contexte navigateur Omega.", {"type": "object", "properties": {}}, "browser", "low", True, False),
            ]
        )
    if config is not None and config.desktop_enabled:
        tools.extend(
            [
                ToolDefinition("desktop_screenshot", "Desktop screenshot", "Capture visible du desktop dans le workspace Omega.", {"type": "object", "properties": {}}, "desktop", "medium", True, False),
                ToolDefinition("desktop_locate_text_stub", "Desktop locate text stub", "Stub OCR desktop v0.1 sans action sur l'ecran.", {"type": "object", "properties": {"text": {"type": "string"}}}, "desktop", "low", True, False),
                ToolDefinition("desktop_click", "Desktop click", "Clique a des coordonnees ecran apres approval obligatoire.", {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}, "desktop", "high", True, True),
                ToolDefinition("desktop_type", "Desktop type", "Saisie clavier visible apres approval obligatoire.", {"type": "object", "properties": {"text": {"type": "string"}, "interval": {"type": "number"}}}, "desktop", "high", True, True),
                ToolDefinition("desktop_hotkey", "Desktop hotkey", "Raccourci clavier visible apres approval obligatoire.", {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}}}}, "desktop", "high", True, True),
            ]
        )
    return tools


class ToolsRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def list(self) -> list[ToolDefinition]:
        return list_tools(self.config)

    def get(self, tool_id: str) -> ToolDefinition | None:
        return next((tool for tool in self.list() if tool.id == tool_id), None)


HANDLERS = {
    "list_files": lambda cfg, args: _list_files(cfg, str(args.get("relative_path", "."))),
    "read_file": lambda cfg, args: _read_file(cfg, str(args.get("relative_path", ""))),
    "write_file": lambda cfg, args: _write_file(cfg, str(args.get("relative_path", "")), str(args.get("content", ""))),
    "append_file": lambda cfg, args: _append_file(cfg, str(args.get("relative_path", "")), str(args.get("content", ""))),
    "delete_file": lambda cfg, args: _delete_file(cfg, str(args.get("relative_path", ""))),
    "create_directory": lambda cfg, args: _create_directory(cfg, str(args.get("relative_path", ""))),
    "delete_directory": lambda cfg, args: _delete_directory(cfg, str(args.get("relative_path", ""))),
    "move_file": lambda cfg, args: _move_file(cfg, str(args.get("source_path", "")), str(args.get("destination_path", ""))),
    "copy_file": lambda cfg, args: _copy_file(cfg, str(args.get("source_path", "")), str(args.get("destination_path", ""))),
    "list_tree": lambda cfg, args: _list_tree(cfg, str(args.get("relative_path", ".")), int(args.get("max_entries", 200))),
    "file_exists": lambda cfg, args: _file_exists(cfg, str(args.get("relative_path", ""))),
    "run_shell": lambda cfg, args: _run_shell(cfg, str(args.get("command", "")), str(args.get("cwd", ".")), int(args.get("timeout_seconds", 60))),
    "remember": lambda cfg, args: _remember(cfg, str(args.get("content", "")), str(args.get("tags", ""))),
    "recall": lambda cfg, args: _recall(cfg, str(args.get("query", ""))),
    "search_memory": lambda cfg, args: _recall(cfg, str(args.get("query", ""))),
    "git_status": lambda cfg, args: git_status(cfg),
    "git_diff": lambda cfg, args: git_diff(cfg),
    "git_log": lambda cfg, args: git_log(cfg),
    "git_branch": lambda cfg, args: git_branch(cfg),
    "git_show": lambda cfg, args: git_show(cfg, str(args.get("ref", "HEAD"))),
    "git_add": lambda cfg, args: git_add(cfg, str(args.get("relative_path", "."))),
    "git_commit": lambda cfg, args: git_commit(cfg, str(args.get("message", ""))),
    "git_restore_file": lambda cfg, args: git_restore_file(cfg, str(args.get("relative_path", ""))),
    "system_info": lambda cfg, args: system_info(cfg),
    "browser_open_url": lambda cfg, args: _browser_open_url(cfg, str(args.get("url", ""))),
    "browser_get_title": lambda cfg, args: _browser_get_title(cfg),
    "browser_screenshot": lambda cfg, args: _browser_screenshot(cfg, bool(args.get("full_page", True))),
    "browser_click": lambda cfg, args: _browser_click(cfg, str(args.get("selector", ""))),
    "browser_type": lambda cfg, args: _browser_type(cfg, str(args.get("selector", "")), str(args.get("text", ""))),
    "browser_extract_text": lambda cfg, args: _browser_extract_text(cfg, str(args.get("selector", "body")), int(args.get("limit", 12000))),
    "browser_close": lambda cfg, args: _browser_close(cfg),
    "desktop_screenshot": lambda cfg, args: _desktop_screenshot(cfg),
    "desktop_locate_text_stub": lambda cfg, args: _desktop_locate_text_stub(cfg, str(args.get("text", ""))),
    "desktop_click": lambda cfg, args: _desktop_click(cfg, int(args.get("x", 0)), int(args.get("y", 0))),
    "desktop_type": lambda cfg, args: _desktop_type(cfg, str(args.get("text", "")), float(args.get("interval", 0.02))),
    "desktop_hotkey": lambda cfg, args: _desktop_hotkey(cfg, args.get("keys", [])),
    "invoke_connector_operation": lambda cfg, args: ConnectorsRegistry(cfg).invoke_operation(
        str(args.get("connector_id", "")),
        str(args.get("operation_id", "")),
        dict(args.get("arguments") or {}),
    ),
}
