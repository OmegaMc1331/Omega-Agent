from __future__ import annotations

MODEL_SELECTION_PRIORITY = ("session", "project", "agent_profile", "global", "env")


def preference_priority() -> tuple[str, ...]:
    return MODEL_SELECTION_PRIORITY
