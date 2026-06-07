from __future__ import annotations

import platform

from omega_agent.config import OmegaConfig


def system_info(config: OmegaConfig) -> str:
    return "\n".join(
        [
            f"platform={platform.platform()}",
            f"python={platform.python_version()}",
            f"workspace={config.workspace}",
            f"safe_mode={config.safe_mode}",
        ]
    )
