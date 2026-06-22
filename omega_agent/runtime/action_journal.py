from __future__ import annotations

from dataclasses import dataclass

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

READ_ONLY_TOOLS = {"read_file", "list_files", "list_tree", "file_exists", "git_status", "git_diff", "git_log", "git_branch", "git_show", "recall", "search_memory", "system_info"}
REVERSIBLE_WRITE_TOOLS = {"write_file", "append_file", "create_directory", "copy_file", "git_add", "git_commit", "remember"}
DESTRUCTIVE_WRITE_TOOLS = {"delete_file", "delete_directory", "move_file", "git_restore_file"}
EXTERNAL_SIDE_EFFECT_TOOLS = {"git_push", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}
SYSTEM_SENSITIVE_TOOLS = {"sudo", "runas"}

FILE_MUTATION_TOOLS = {
    "write_file",
    "append_file",
    "delete_file",
    "delete_directory",
    "move_file",
    "copy_file",
    "create_directory",
}


@dataclass(frozen=True)
class JournalAction:
    id: str
    run_id: str
    step_id: str | None
    action_type: str
    tool_name: str | None
    arguments: dict
    policy_decision: dict
    budget_decision: dict
    risk_level: str
    status: str
    observation: dict | None
    created_at: str
    completed_at: str | None
    rollback_available: bool
    snapshot_id: str | None
    metadata: dict

    def as_api(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "arguments": redact(self.arguments),
            "policy_decision": redact(self.policy_decision),
            "budget_decision": redact(self.budget_decision),
            "risk_level": self.risk_level,
            "status": self.status,
            "observation": redact(self.observation),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "rollback_available": self.rollback_available,
            "snapshot_id": self.snapshot_id,
            "metadata": redact(self.metadata),
        }


class ActionJournalStore:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def list(self, run_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM action_journal"
        params: list[object] = []
        if run_id:
            query += " WHERE run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [redact(dict(row)) for row in rows]

    def successful_tool_sequences(self, limit: int = 200) -> dict[str, list[str]]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT action_journal.run_id, action_journal.tool_name, action_journal.action_type
                FROM action_journal
                JOIN runs ON runs.id = action_journal.run_id
                WHERE runs.status = 'succeeded' AND action_journal.status = 'succeeded'
                ORDER BY action_journal.run_id, action_journal.created_at
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        sequences: dict[str, list[str]] = {}
        for row in rows:
            sequences.setdefault(row["run_id"], []).append(str(row["tool_name"] or row["action_type"]))
        return redact(sequences)


def classify_action(tool_name: str, arguments: dict | None = None) -> str:
    command = str((arguments or {}).get("command") or "").lower()
    if tool_name == "invoke_connector_operation":
        category = str((arguments or {}).get("action_category") or "").lower()
        if category in {"read_only", "reversible_write", "destructive_write", "external_side_effect", "system_sensitive"}:
            return category
        return "read_only"
    if tool_name in READ_ONLY_TOOLS:
        return "read_only"
    if tool_name in REVERSIBLE_WRITE_TOOLS:
        return "reversible_write"
    if tool_name in DESTRUCTIVE_WRITE_TOOLS:
        return "destructive_write"
    if tool_name in EXTERNAL_SIDE_EFFECT_TOOLS:
        return "external_side_effect"
    if tool_name in SYSTEM_SENSITIVE_TOOLS:
        return "system_sensitive"
    if tool_name == "run_shell":
        if any(token in command for token in ("del ", "erase ", "move ", "copy ", "mkdir ", "rmdir ", "git add", "git commit", "npm ", "python ", ">")):
            return "reversible_write"
        return "read_only"
    return "read_only"


def tool_modifies_files(tool_name: str, arguments: dict | None = None) -> bool:
    if tool_name == "invoke_connector_operation":
        args = arguments or {}
        return str(args.get("connector_id")) == "filesystem" and str(args.get("operation_id")) in {"write_file", "delete_file"}
    if tool_name in FILE_MUTATION_TOOLS:
        return True
    if tool_name == "run_shell":
        command = str((arguments or {}).get("command") or "").lower()
        return any(token in command for token in ("del ", "erase ", "move ", "copy ", "mkdir ", "rmdir ", "git add", "git commit", ">"))
    return False


def snapshot_paths_for_tool(tool_name: str, arguments: dict | None = None) -> list[str]:
    args = arguments or {}
    if tool_name == "invoke_connector_operation" and str(args.get("connector_id")) == "filesystem":
        operation_args = args.get("arguments") or args.get("operation_arguments") or {}
        if str(args.get("operation_id")) in {"write_file", "delete_file"}:
            return [str(operation_args.get("relative_path") or operation_args.get("path") or "")]
    if tool_name in {"write_file", "append_file", "delete_file", "delete_directory", "create_directory"}:
        return [str(args.get("relative_path") or args.get("path") or ".")]
    if tool_name == "move_file":
        return [str(args.get("source_path") or args.get("source") or ""), str(args.get("destination_path") or args.get("destination") or "")]
    if tool_name == "copy_file":
        return [str(args.get("destination_path") or args.get("destination") or args.get("target") or "")]
    return []
