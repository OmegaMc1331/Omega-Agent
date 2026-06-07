__all__ = ["INSTRUCTIONS", "OmegaRuntime", "build_agent"]


def __getattr__(name: str):
    if name in __all__:
        from .agent import INSTRUCTIONS, OmegaRuntime, build_agent

        values = {"INSTRUCTIONS": INSTRUCTIONS, "OmegaRuntime": OmegaRuntime, "build_agent": build_agent}
        return values[name]
    raise AttributeError(name)
