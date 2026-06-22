from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_models import BudgetContext, BudgetUsage, EffectiveBudget, parse_json
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class QuotaTracker:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def get_usage_value(self, context: BudgetContext, metric: str) -> float:
        usage_id = _usage_id(context, metric)
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT used_value FROM budget_usage WHERE id = ?", (usage_id,)).fetchone()
        return float(row["used_value"] or 0) if row else 0.0

    def record(
        self,
        context: BudgetContext,
        metric: str,
        increment: float,
        effective: EffectiveBudget,
        *,
        absolute: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetUsage:
        usage_id = _usage_id(context, metric)
        current = self.get_usage_value(context, metric)
        value = float(increment) if absolute else current + float(increment)
        limit = _numeric_limit(effective.limits.get(metric))
        status = _status(value, limit, self.config.governance_budgets_warning_threshold)
        profile_id = effective.limiting_profiles.get(metric)
        now = datetime.now(timezone.utc).isoformat()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO budget_usage(
                    id, profile_id, run_id, workflow_run_id, session_id, project_id,
                    metric, used_value, limit_value, status, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id=excluded.profile_id,
                    used_value=excluded.used_value,
                    limit_value=excluded.limit_value,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    usage_id,
                    profile_id,
                    context.run_id,
                    context.workflow_run_id,
                    context.session_id,
                    context.project_id,
                    metric,
                    value,
                    limit,
                    status,
                    now,
                    json.dumps(redact(metadata or {}), ensure_ascii=False),
                ),
            )
        if status == "warning":
            self.events.add(
                "budget.warning",
                {"run_id": context.run_id, "workflow_run_id": context.workflow_run_id, "metric": metric, "used_value": value, "limit_value": limit},
                session_id=context.session_id,
            )
        return self.get(usage_id)

    def get(self, usage_id: str) -> BudgetUsage | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM budget_usage WHERE id = ?", (usage_id,)).fetchone()
        return _usage(row) if row else None

    def list(
        self,
        *,
        run_id: str | None = None,
        workflow_run_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        limit: int = 500,
    ) -> list[BudgetUsage]:
        query = "SELECT * FROM budget_usage"
        clauses = []
        params: list[Any] = []
        for column, value in [
            ("run_id", run_id),
            ("workflow_run_id", workflow_run_id),
            ("session_id", session_id),
            ("project_id", project_id),
        ]:
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 2000)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_usage(row) for row in rows]


def _usage_id(context: BudgetContext, metric: str) -> str:
    material = "|".join(
        [
            context.run_id or "",
            context.workflow_run_id or "",
            context.session_id or "",
            context.project_id or "",
            metric,
        ]
    )
    return "budget-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _numeric_limit(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(value: float, limit: float | None, threshold: float) -> str:
    if limit is None:
        return "ok"
    if value > limit:
        return "exceeded"
    if limit == 0:
        return "warning" if value == 0 else "exceeded"
    return "warning" if value >= limit * threshold else "ok"


def _usage(row) -> BudgetUsage:
    return BudgetUsage(
        id=row["id"],
        profile_id=row["profile_id"],
        run_id=row["run_id"],
        workflow_run_id=row["workflow_run_id"],
        session_id=row["session_id"],
        project_id=row["project_id"],
        metric=row["metric"],
        used_value=float(row["used_value"] or 0),
        limit_value=float(row["limit_value"]) if row["limit_value"] is not None else None,
        status=row["status"],
        updated_at=row["updated_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )
