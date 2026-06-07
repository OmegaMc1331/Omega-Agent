from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from omega_agent.compat import function_tool
from omega_agent.config import OmegaConfig
from omega_agent.runtime.project_context import active_config
from omega_agent.security import log_action


def memory_db_path(config: OmegaConfig) -> str:
    return str(config.workspace / ".omega" / "memory.db")


def init_db(config: OmegaConfig | None = None) -> None:
    cfg = config or OmegaConfig.from_env()
    cfg.ensure_dirs()
    with sqlite3.connect(memory_db_path(cfg)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )


def _remember(config: OmegaConfig, content: str, tags: str) -> str:
    init_db(config)
    with sqlite3.connect(memory_db_path(config)) as conn:
        conn.execute(
            "INSERT INTO memories(content, tags, created_at) VALUES (?, ?, ?)",
            (content, tags, datetime.now(timezone.utc).isoformat()),
        )
    log_action(config, "remember", {"tags": tags})
    return "Mémoire enregistrée."


def _recall(config: OmegaConfig, query: str) -> str:
    init_db(config)
    like = f"%{query}%"
    with sqlite3.connect(memory_db_path(config)) as conn:
        rows = conn.execute(
            """
            SELECT id, content, tags, created_at
            FROM memories
            WHERE content LIKE ? OR tags LIKE ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (like, like),
        ).fetchall()
    log_action(config, "recall", {"query": query})
    if not rows:
        return "Aucune mémoire trouvée."
    return "\n".join(f"#{id} [{tags}] {content} ({created_at})" for id, content, tags, created_at in rows)


@function_tool
def remember(content: str, tags: str) -> str:
    """Store a long-lived memory for Omega Agent."""
    return _remember(active_config(), content, tags)


@function_tool
def recall(query: str) -> str:
    """Search Omega Agent memories with a simple LIKE query."""
    return _recall(active_config(), query)
