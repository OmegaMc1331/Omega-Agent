from __future__ import annotations

from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.storage import connect_db, db_path, migrate


def runtime_db_path(config: OmegaConfig) -> Path:
    return db_path(config)


def connect_runtime_db(config: OmegaConfig):
    migrate(config)
    return connect_db(config)
