from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F", bound=Callable)

try:
    from agents import function_tool
except ModuleNotFoundError:

    def function_tool(func: F) -> F:
        return func
