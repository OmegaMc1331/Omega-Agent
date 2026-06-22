from __future__ import annotations

from pathlib import Path
from threading import Lock

from omega_agent.config import OmegaConfig
from omega_agent.storage import connect_db, db_path, migrate

_MIGRATION_LOCK = Lock()
_MIGRATED_DB_PATHS: set[Path] = set()


def runtime_db_path(config: OmegaConfig) -> Path:
    return db_path(config)


def connect_runtime_db(config: OmegaConfig):
    path = runtime_db_path(config)
    if path not in _MIGRATED_DB_PATHS:
        with _MIGRATION_LOCK:
            if path not in _MIGRATED_DB_PATHS:
                migrate(config)
                _MIGRATED_DB_PATHS.add(path)
    return connect_db(config)
