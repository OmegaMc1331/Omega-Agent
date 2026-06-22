from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.security.sandbox import is_path_inside_workspace, safe_path


@dataclass(frozen=True)
class FileSnapshot:
    id: str
    run_id: str
    action_id: str | None
    workspace_path: str
    absolute_path: str
    snapshot_path: str | None
    existed_before: bool
    content_hash_before: str | None
    content_hash_after: str | None
    size_before: int | None
    size_after: int | None
    created_at: str
    restored_at: str | None
    metadata: dict

    def as_api(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "action_id": self.action_id,
            "workspace_path": self.workspace_path,
            "absolute_path": self.absolute_path,
            "snapshot_path": self.snapshot_path,
            "existed_before": self.existed_before,
            "content_hash_before": self.content_hash_before,
            "content_hash_after": self.content_hash_after,
            "size_before": self.size_before,
            "size_after": self.size_after,
            "created_at": self.created_at,
            "restored_at": self.restored_at,
            "metadata": redact(self.metadata),
        }


class SnapshotStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    @property
    def root(self) -> Path:
        # Stored inside the workspace boundary so snapshots never require global
        # filesystem access and are governed by the same sandbox as workspace files.
        return self.config.workspace / ".omega" / "snapshots"

    def create_for_paths(self, run_id: str, action_id: str | None, paths: list[str | Path]) -> list[FileSnapshot]:
        if not self.config.runtime_snapshots_enabled:
            return []
        snapshots: list[FileSnapshot] = []
        for raw_path in [item for item in paths if str(item or "").strip()]:
            snapshots.append(self._create_one(run_id, action_id, raw_path))
        if snapshots and action_id:
            rollback_available = any(_snapshot_can_rollback(snapshot) for snapshot in snapshots)
            with connect_runtime_db(self.config) as conn:
                conn.execute(
                    "UPDATE action_journal SET snapshot_id = ?, rollback_available = ? WHERE id = ?",
                    (snapshots[0].id, 1 if rollback_available else 0, action_id),
                )
        return snapshots

    def list(self, run_id: str | None = None, limit: int = 100) -> list[FileSnapshot]:
        query = "SELECT * FROM file_snapshots"
        params: list[object] = []
        if run_id:
            query += " WHERE run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [snapshot_from_row(row) for row in rows]

    def get(self, snapshot_id: str) -> FileSnapshot | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM file_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return snapshot_from_row(row) if row else None

    def update_hashes_after_action(self, action_id: str) -> None:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM file_snapshots WHERE action_id = ?", (action_id,)).fetchall()
            for row in rows:
                snapshot = snapshot_from_row(row)
                path = Path(snapshot.absolute_path)
                size_after = _path_size(path) if path.exists() else None
                hash_after = _hash_path(path) if path.exists() and path.is_file() else None
                conn.execute(
                    "UPDATE file_snapshots SET content_hash_after = ?, size_after = ? WHERE id = ?",
                    (hash_after, size_after, snapshot.id),
                )

    def _create_one(self, run_id: str, action_id: str | None, raw_path: str | Path) -> FileSnapshot:
        absolute = safe_path(self.config, str(raw_path))
        if not is_path_inside_workspace(absolute, self.config.workspace):
            raise PermissionError("Snapshot refuse: chemin hors workspace.")
        workspace_path = absolute.relative_to(self.config.workspace.resolve()).as_posix()
        snapshot_id = uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        existed_before = absolute.exists()
        metadata: dict = {"rollback_available": True}
        snapshot_path: str | None = None
        size_before: int | None = None
        hash_before: str | None = None

        if existed_before:
            size_before = _path_size(absolute)
            max_bytes = max(1, int(self.config.runtime_snapshots_max_file_size_mb)) * 1024 * 1024
            if size_before is not None and size_before > max_bytes:
                metadata.update({"too_large": True, "rollback_available": False, "max_file_size_mb": self.config.runtime_snapshots_max_file_size_mb})
            else:
                target_dir = self.root / run_id / snapshot_id
                target_dir.mkdir(parents=True, exist_ok=True)
                if absolute.is_dir():
                    target = target_dir / "content"
                    shutil.copytree(absolute, target)
                    metadata["kind"] = "directory"
                else:
                    target = target_dir / absolute.name
                    shutil.copy2(absolute, target)
                    hash_before = _hash_file(absolute)
                    metadata["kind"] = "file"
                snapshot_path = str(target)
        else:
            metadata.update({"kind": "missing", "rollback_available": True})

        snapshot = FileSnapshot(
            id=snapshot_id,
            run_id=run_id,
            action_id=action_id,
            workspace_path=workspace_path,
            absolute_path=str(absolute),
            snapshot_path=snapshot_path,
            existed_before=existed_before,
            content_hash_before=hash_before,
            content_hash_after=None,
            size_before=size_before,
            size_after=None,
            created_at=created_at,
            restored_at=None,
            metadata=metadata,
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO file_snapshots(
                    id, run_id, action_id, workspace_path, absolute_path, snapshot_path,
                    existed_before, content_hash_before, content_hash_after, size_before,
                    size_after, created_at, restored_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.run_id,
                    snapshot.action_id,
                    snapshot.workspace_path,
                    snapshot.absolute_path,
                    snapshot.snapshot_path,
                    1 if snapshot.existed_before else 0,
                    snapshot.content_hash_before,
                    snapshot.content_hash_after,
                    snapshot.size_before,
                    snapshot.size_after,
                    snapshot.created_at,
                    snapshot.restored_at,
                    json.dumps(redact(snapshot.metadata), ensure_ascii=False),
                ),
            )
        self.events.add("snapshot.created", {"run_id": run_id, "snapshot_id": snapshot.id, "action_id": action_id, "workspace_path": workspace_path}, session_id=None)
        return snapshot


def snapshot_from_row(row) -> FileSnapshot:
    metadata = json.loads(row["metadata_json"] or "{}")
    return FileSnapshot(
        id=row["id"],
        run_id=row["run_id"],
        action_id=row["action_id"],
        workspace_path=row["workspace_path"],
        absolute_path=row["absolute_path"],
        snapshot_path=row["snapshot_path"],
        existed_before=bool(row["existed_before"]),
        content_hash_before=row["content_hash_before"],
        content_hash_after=row["content_hash_after"],
        size_before=row["size_before"],
        size_after=row["size_after"],
        created_at=row["created_at"],
        restored_at=row["restored_at"],
        metadata=metadata,
    )


def _snapshot_can_rollback(snapshot: FileSnapshot) -> bool:
    return bool(snapshot.metadata.get("rollback_available", True))


def _path_size(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _hash_path(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return _hash_file(path)


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
