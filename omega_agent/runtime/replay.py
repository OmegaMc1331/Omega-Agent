from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class ReplayStore:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def replay_run(self, run_id: str, dry_run: bool = True) -> dict:
        with connect_runtime_db(self.config) as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Run introuvable.")
            actions = conn.execute("SELECT * FROM action_journal WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        return redact(
            {
                "run_id": run_id,
                "dry_run": dry_run,
                "status": "completed",
                "actions": [dict(action) for action in actions],
                "note": "Replay v1 reconstruit le plan d'execution; dry_run=false n'est pas execute automatiquement.",
            }
        )
