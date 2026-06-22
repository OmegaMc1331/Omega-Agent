from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowTrigger:
    id: str
    workflow_id: str
    type: str
    enabled: bool
    config: dict[str, Any]

    def as_api(self) -> dict[str, Any]:
        return self.__dict__


def list_workflow_triggers() -> list[WorkflowTrigger]:
    return []
