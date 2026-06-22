from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.snapshots import FileSnapshot, SnapshotStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.security.sandbox import is_path_inside_workspace


@dataclass(frozen=True)
class RollbackResult:
    id: str
    run_id: str
    snapshot_id: str | None
    action_id: str | None
    status: str
    restored: list[str]
    deleted: list[str]
    skipped: list[str]
    errors: list[str]
    warning: str = ""

    def as_api(self) -> dict:
        return redact(
            {
                "id": self.id,
                "run_id": self.run_id,
                "snapshot_id": self.snapshot_id,
                "action_id": self.action_id,
                "status": self.status,
                "restored": self.restored,
                "deleted": self.deleted,
                "skipped": self.skipped,
                "errors": self.errors,
                "warning": self.warning,
            }
        )


class RollbackManager:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.snapshots = SnapshotStore(config)
        self.events = EventsStore(config)
        self.budgets = BudgetEnforcer(config)

    def rollback_snapshot(self, snapshot_id: str, reason: str = "manual") -> RollbackResult:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError("Snapshot introuvable.")
        budget_context = self.budgets.context(run_id=snapshot.run_id)
        budget_decision = self.budgets.check_metric(budget_context, "max_rollbacks", action_category="reversible_write", risk_level="medium")
        if self.config.governance_budgets_enforce and budget_decision.action in {"pause", "deny", "require_approval"}:
            raise PermissionError(budget_decision.reason)
        event_id = self._create_event(snapshot.run_id, snapshot.id, snapshot.action_id, reason)
        self.events.add("rollback.started", {"run_id": snapshot.run_id, "snapshot_id": snapshot.id, "action_id": snapshot.action_id})
        try:
            result = self._restore_snapshot(event_id, snapshot)
            self._complete_event(event_id, result.status, None, result.as_api())
            if snapshot.action_id:
                with connect_runtime_db(self.config) as conn:
                    conn.execute("UPDATE action_journal SET status = 'rolled_back' WHERE id = ?", (snapshot.action_id,))
            self.events.add("rollback.completed", result.as_api())
            self.budgets.record_usage(budget_context, "max_rollbacks", 1, metadata={"snapshot_id": snapshot.id, "status": result.status})
            return result
        except Exception as exc:
            result = RollbackResult(event_id, snapshot.run_id, snapshot.id, snapshot.action_id, "failed", [], [], [], [str(exc)])
            self._complete_event(event_id, "failed", str(exc), result.as_api())
            self.events.add("rollback.failed", result.as_api())
            self.budgets.record_usage(budget_context, "max_rollbacks", 1, metadata={"snapshot_id": snapshot.id, "status": "failed"})
            return result

    def rollback_run(self, run_id: str, reason: str = "manual") -> dict:
        snapshots = self.snapshots.list(run_id=run_id, limit=1000)
        restored: list[str] = []
        deleted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for snapshot in sorted(snapshots, key=lambda item: item.created_at, reverse=True):
            if snapshot.restored_at:
                skipped.append(snapshot.workspace_path)
                continue
            result = self.rollback_snapshot(snapshot.id, reason=reason)
            restored.extend(result.restored)
            deleted.extend(result.deleted)
            skipped.extend(result.skipped)
            errors.extend(result.errors)
        return redact({"run_id": run_id, "restored": restored, "deleted": deleted, "skipped": skipped, "errors": errors})

    def _restore_snapshot(self, event_id: str, snapshot: FileSnapshot) -> RollbackResult:
        target = Path(snapshot.absolute_path).expanduser().resolve()
        if not is_path_inside_workspace(target, self.config.workspace):
            raise PermissionError("Rollback refuse: chemin hors workspace.")
        warnings: list[str] = []
        restored: list[str] = []
        deleted: list[str] = []
        skipped: list[str] = []
        if snapshot.metadata.get("too_large"):
            skipped.append(snapshot.workspace_path)
            return RollbackResult(event_id, snapshot.run_id, snapshot.id, snapshot.action_id, "failed", [], [], skipped, ["Snapshot trop volumineux: rollback indisponible."])

        if snapshot.existed_before:
            if not snapshot.snapshot_path:
                raise FileNotFoundError("Snapshot physique introuvable.")
            source = Path(snapshot.snapshot_path).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError("Snapshot physique introuvable.")
            if snapshot.content_hash_after and target.exists() and target.is_file():
                current_hash = _hash_file(target)
                if current_hash != snapshot.content_hash_after:
                    warnings.append("Le fichier actuel a change depuis l'action; restauration forcee.")
            if source.is_dir():
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.copytree(source, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            restored.append(snapshot.workspace_path)
        else:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                deleted.append(snapshot.workspace_path)
            else:
                skipped.append(snapshot.workspace_path)

        completed_at = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE file_snapshots SET restored_at = ? WHERE id = ?", (completed_at, snapshot.id))
        return RollbackResult(event_id, snapshot.run_id, snapshot.id, snapshot.action_id, "succeeded", restored, deleted, skipped, [], "; ".join(warnings))

    def _create_event(self, run_id: str, snapshot_id: str | None, action_id: str | None, reason: str) -> str:
        event_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO rollback_events(id, run_id, snapshot_id, action_id, status, reason, created_at, metadata_json)
                VALUES (?, ?, ?, ?, 'running', ?, ?, '{}')
                """,
                (event_id, run_id, snapshot_id, action_id, reason, now),
            )
        return event_id

    def _complete_event(self, event_id: str, status: str, error: str | None, metadata: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE rollback_events SET status = ?, completed_at = ?, error = ?, metadata_json = ? WHERE id = ?",
                (status, now, error, json.dumps(redact(metadata), ensure_ascii=False), event_id),
            )


def _hash_file(path: Path) -> str:
    import hashlib

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
