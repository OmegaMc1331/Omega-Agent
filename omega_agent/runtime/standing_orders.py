from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security import log_action

VALID_SCOPES = {"global", "project", "session"}


@dataclass(frozen=True)
class StandingOrder:
    id: str
    title: str
    content: str
    scope: str
    enabled: bool
    priority: int
    created_at: str
    updated_at: str


class StandingOrdersStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def create(self, title: str, content: str, scope: str = "global", enabled: bool = True, priority: int = 100) -> StandingOrder:
        if scope not in VALID_SCOPES:
            raise ValueError("Scope standing order invalide.")
        if not content.strip():
            raise ValueError("Standing order vide.")
        now = utc_now()
        order = StandingOrder(uuid4().hex, title.strip() or "Standing order", content.strip(), scope, enabled, int(priority), now, now)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO standing_orders(id, title, content, scope, enabled, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order.id, order.title, order.content, order.scope, int(order.enabled), order.priority, order.created_at, order.updated_at),
            )
        log_action(self.config, "standing_order_created", {"order_id": order.id, "scope": scope})
        return order

    def list(self, include_disabled: bool = True, scope: str | None = None) -> list[StandingOrder]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_disabled:
            clauses.append("enabled = 1")
        if scope:
            if scope not in VALID_SCOPES:
                raise ValueError("Scope standing order invalide.")
            clauses.append("scope = ?")
            params.append(scope)
        sql = "SELECT id, title, content, scope, enabled, priority, created_at, updated_at FROM standing_orders"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY priority ASC, updated_at DESC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    def active_for_context(self, session_id: str | None = None, project_id: str | None = None) -> list[StandingOrder]:
        # v0 scopes are declarative; project/session identifiers are carried in content/title until scoped ownership lands.
        return self.list(include_disabled=False)

    def get(self, order_id: str) -> StandingOrder | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                "SELECT id, title, content, scope, enabled, priority, created_at, updated_at FROM standing_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def update(
        self,
        order_id: str,
        title: str | None = None,
        content: str | None = None,
        scope: str | None = None,
        enabled: bool | None = None,
        priority: int | None = None,
    ) -> StandingOrder | None:
        current = self.get(order_id)
        if current is None:
            return None
        next_scope = scope or current.scope
        if next_scope not in VALID_SCOPES:
            raise ValueError("Scope standing order invalide.")
        now = utc_now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE standing_orders
                SET title = ?, content = ?, scope = ?, enabled = ?, priority = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title.strip() if title is not None and title.strip() else current.title,
                    content.strip() if content is not None and content.strip() else current.content,
                    next_scope,
                    int(current.enabled if enabled is None else enabled),
                    current.priority if priority is None else int(priority),
                    now,
                    order_id,
                ),
            )
        log_action(self.config, "standing_order_updated", {"order_id": order_id})
        return self.get(order_id)

    def delete(self, order_id: str) -> bool:
        with connect_runtime_db(self.config) as conn:
            result = conn.execute("DELETE FROM standing_orders WHERE id = ?", (order_id,))
        if result.rowcount:
            log_action(self.config, "standing_order_deleted", {"order_id": order_id})
        return result.rowcount > 0

    def _from_row(self, row) -> StandingOrder:
        return StandingOrder(row["id"], row["title"], row["content"], row["scope"], bool(row["enabled"]), int(row["priority"]), row["created_at"], row["updated_at"])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
