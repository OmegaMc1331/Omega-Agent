from __future__ import annotations

import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.security.redaction import redact


PERF_STEPS = [
    "request_received",
    "session_loaded",
    "context_built",
    "memory_loaded",
    "skills_loaded",
    "tools_loaded",
    "provider_started",
    "first_event_sent",
    "first_token_received",
    "provider_completed",
    "response_persisted",
    "total_duration",
]


@dataclass
class PerformanceTrace:
    trace_id: str
    session_id: str | None
    message_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    steps_ms: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    completed: bool = False
    failed: bool = False

    def as_api(self) -> dict:
        return redact(asdict(self))


class PerformanceStore:
    def __init__(self, config: OmegaConfig, maxlen: int = 100):
        self.config = config
        self._traces: deque[PerformanceTrace] = deque(maxlen=maxlen)
        self._lock = Lock()

    def start(self, session_id: str | None = None, metadata: dict | None = None) -> "PerformanceTimer":
        trace = PerformanceTrace(trace_id=uuid4().hex, session_id=session_id, metadata=metadata or {})
        with self._lock:
            self._traces.appendleft(trace)
        timer = PerformanceTimer(self.config, trace)
        timer.mark("request_received")
        return timer

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return [trace.as_api() for trace in list(self._traces)[:limit]]


class PerformanceTimer:
    def __init__(self, config: OmegaConfig, trace: PerformanceTrace):
        self.config = config
        self.trace = trace
        self._started = time.perf_counter()
        self._last = self._started

    @property
    def trace_id(self) -> str:
        return self.trace.trace_id

    def set_message_id(self, message_id: str | None) -> None:
        self.trace.message_id = message_id

    def annotate(self, **metadata) -> None:
        self.trace.metadata.update(redact(metadata))

    def mark(self, step: str) -> None:
        now = time.perf_counter()
        self.trace.steps_ms[step] = round((now - self._last) * 1000, 2)
        self._last = now

    @contextmanager
    def step(self, step: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.trace.steps_ms[step] = round((time.perf_counter() - start) * 1000, 2)
            self._last = time.perf_counter()

    def complete(self, events: EventsStore | None = None, failed: bool = False) -> None:
        self.trace.steps_ms["total_duration"] = round((time.perf_counter() - self._started) * 1000, 2)
        self.trace.completed = not failed
        self.trace.failed = failed
        if self.config.perf_logging and events is not None:
            events.add("performance.chat_trace", self.trace.as_api(), session_id=self.trace.session_id)
