from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.events.event_store import EventStore
from omega_agent.events.protocol import OmegaEvent


class EventReplay:
    def __init__(self, config: OmegaConfig):
        self.store = EventStore(config)

    def replay_events(
        self,
        *,
        since_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[OmegaEvent]:
        return self.store.replay(since_id=since_id, session_id=session_id, run_id=run_id, limit=limit, for_ui=True)
