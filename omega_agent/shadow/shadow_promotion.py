from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.shadow.shadow_runner import ShadowRunner


class ShadowPromoter:
    def __init__(self, runner: "ShadowRunner"):
        self.runner = runner

    def promote(self, shadow_run_id: str, approved_by: str | None = None):
        return self.runner.promote_to_live(shadow_run_id, approved_by=approved_by)
