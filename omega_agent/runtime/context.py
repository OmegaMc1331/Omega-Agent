from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Literal

RuntimeMode = Literal["cli", "server", "test"]


@dataclass(frozen=True)
class RuntimeContext:
    mode: RuntimeMode


_RUNTIME_CONTEXT: ContextVar[RuntimeContext] = ContextVar(
    "omega_runtime_context",
    default=RuntimeContext(mode="server"),
)


def current_runtime_context() -> RuntimeContext:
    return _RUNTIME_CONTEXT.get()


def current_runtime_mode() -> RuntimeMode:
    return current_runtime_context().mode


@contextmanager
def runtime_context(mode: RuntimeMode) -> Iterator[RuntimeContext]:
    context = RuntimeContext(mode=mode)
    token = _RUNTIME_CONTEXT.set(context)
    try:
        yield context
    finally:
        _RUNTIME_CONTEXT.reset(token)
