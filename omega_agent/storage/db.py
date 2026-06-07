from __future__ import annotations

import sqlite3
from pathlib import Path

from omega_agent.config import OmegaConfig


def db_path(config: OmegaConfig) -> Path:
    config.ensure_dirs()
    return (config.db_path or (config.workspace / ".omega" / "omega.db")).expanduser().resolve()


def connect_db(config: OmegaConfig) -> sqlite3.Connection:
    path = db_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
