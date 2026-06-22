from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.runtime.project_memory import ProjectMemoryStore


def compact_project_memory(config: OmegaConfig, project_id: str) -> dict:
    return ProjectMemoryStore(config).compact_project_memory(project_id)
