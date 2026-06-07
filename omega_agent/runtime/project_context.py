from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

from omega_agent.config import OmegaConfig

_ACTIVE_CONFIG: ContextVar[OmegaConfig | None] = ContextVar("omega_active_project_config", default=None)


def active_config() -> OmegaConfig:
    return _ACTIVE_CONFIG.get() or OmegaConfig.from_env()


@contextmanager
def use_project_config(config: OmegaConfig) -> Iterator[None]:
    token = _ACTIVE_CONFIG.set(config)
    try:
        yield
    finally:
        _ACTIVE_CONFIG.reset(token)
