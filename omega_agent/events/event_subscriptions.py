from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class EventSubscription:
    channel: str
    queue: asyncio.Queue

    async def get(self, timeout: float | None = None):
        if timeout is None:
            return await self.queue.get()
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)
