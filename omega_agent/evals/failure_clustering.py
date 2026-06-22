from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL

from omega_agent.config import OmegaConfig
from omega_agent.evals.trace_collector import TraceCollector
from omega_agent.runtime.error_taxonomy import classify_error
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class FailureClustering:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def classify_failure(self, run_id: str) -> dict:
        trace = TraceCollector(self.config).collect_run_trace(run_id)
        run = trace.get("run") or {}
        actions = trace.get("actions") or []
        failed_actions = [item for item in actions if item.get("status") in {"failed", "denied"}]
        if failed_actions:
            action = failed_actions[0]
            text = json.dumps(action.get("observation") or action.get("policy_decision") or {}, ensure_ascii=False)
            classified = classify_error(text, {"run_id": run_id, "tool_name": action.get("tool_name")})
            failure_type = classified.error_type if classified.error_type != "unknown" else f"tool_{action.get('status')}"
            title = f"{action.get('tool_name') or 'tool'} {action.get('status')}"
            return redact({"run_id": run_id, "failure_type": failure_type, "title": title, "summary": classified.summary, "tool_name": action.get("tool_name")})
        if run.get("status") in {"failed", "cancelled", "needs_approval"}:
            classified = classify_error(str(run.get("error") or run.get("status")), {"run_id": run_id})
            return redact({"run_id": run_id, "failure_type": classified.error_type, "title": classified.title, "summary": classified.summary})
        return {"run_id": run_id, "failure_type": "none", "title": "No failure", "summary": ""}

    def cluster_recent_failures(self, limit: int = 100) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            runs = conn.execute(
                "SELECT id FROM runs WHERE status IN ('failed','cancelled','needs_approval') ORDER BY updated_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            action_runs = conn.execute(
                "SELECT DISTINCT run_id AS id FROM action_journal WHERE status IN ('failed','denied') ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        seen = []
        for row in list(runs) + list(action_runs):
            if row["id"] not in seen:
                seen.append(row["id"])
        for run_id in seen[:limit]:
            item = self.classify_failure(run_id)
            if item.get("failure_type") != "none":
                self._upsert_cluster(item)
        return self.list_clusters()

    def list_clusters(self, status: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM failure_clusters"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY count DESC, last_seen_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_cluster_api(row) for row in rows]

    def recovered_failure_patterns(self, limit: int = 100) -> list[dict]:
        """Return failed tool calls from runs that ultimately succeeded and later recovered."""
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT failed.run_id, failed.tool_name, failed.observation_json, failed.created_at
                FROM action_journal AS failed
                JOIN runs ON runs.id = failed.run_id
                WHERE runs.status = 'succeeded'
                  AND failed.status = 'failed'
                  AND EXISTS (
                    SELECT 1 FROM action_journal AS recovered
                    WHERE recovered.run_id = failed.run_id
                      AND recovered.status = 'succeeded'
                      AND COALESCE(recovered.tool_name, '') = COALESCE(failed.tool_name, '')
                      AND recovered.created_at > failed.created_at
                  )
                ORDER BY failed.created_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            redact(
                {
                    "run_id": row["run_id"],
                    "tool_name": row["tool_name"],
                    "observation": json.loads(row["observation_json"] or "{}"),
                    "recovered": True,
                }
            )
            for row in rows
        ]

    def suggest_cluster_fix(self, cluster_id: str) -> dict:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM failure_clusters WHERE id = ?", (cluster_id,)).fetchone()
        if row is None:
            raise ValueError("Cluster introuvable.")
        failure_type = row["failure_type"]
        suggestion = _suggestion_for_failure(failure_type)
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE failure_clusters SET suggested_fix = ? WHERE id = ?", (suggestion, cluster_id))
        return {**_cluster_api(row), "suggested_fix": suggestion}

    def mark_cluster_fixed(self, cluster_id: str, status: str = "fixed") -> dict:
        if status not in {"open", "investigating", "fixed", "ignored"}:
            raise ValueError("Status cluster invalide.")
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE failure_clusters SET status = ? WHERE id = ?", (status, cluster_id))
            row = conn.execute("SELECT * FROM failure_clusters WHERE id = ?", (cluster_id,)).fetchone()
        if row is None:
            raise ValueError("Cluster introuvable.")
        return _cluster_api(row)

    def _upsert_cluster(self, item: dict) -> None:
        failure_type = str(item.get("failure_type") or "unknown")
        title = str(item.get("title") or failure_type)
        cluster_id = uuid5(NAMESPACE_URL, f"omega-failure:{failure_type}:{title.lower()}").hex
        now = datetime.now(timezone.utc).isoformat()
        example = redact({"run_id": item.get("run_id"), "summary": item.get("summary"), "tool_name": item.get("tool_name")})
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM failure_clusters WHERE id = ?", (cluster_id,)).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO failure_clusters(id, title, description, failure_type, count, first_seen_at, last_seen_at, examples_json, suggested_fix, status, metadata_json)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'open', '{}')
                    """,
                    (cluster_id, title, str(item.get("summary") or ""), failure_type, now, now, json.dumps([example], ensure_ascii=False), _suggestion_for_failure(failure_type)),
                )
                return
            examples = json.loads(row["examples_json"] or "[]")
            already_seen = any(existing.get("run_id") == example.get("run_id") for existing in examples if isinstance(existing, dict))
            if not already_seen:
                examples = ([example] + examples)[:10]
            count_sql = "count" if already_seen else "count + 1"
            conn.execute(
                f"UPDATE failure_clusters SET count = {count_sql}, last_seen_at = ?, examples_json = ? WHERE id = ?",
                (now, json.dumps(redact(examples), ensure_ascii=False), cluster_id),
            )


def _cluster_api(row) -> dict:
    item = dict(row)
    try:
        item["examples"] = json.loads(item.get("examples_json") or "[]")
    except json.JSONDecodeError:
        item["examples"] = []
    try:
        item["metadata"] = json.loads(item.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        item["metadata"] = {}
    return redact(item)


def _suggestion_for_failure(failure_type: str) -> str:
    mapping = {
        "command_not_found": "Documenter la dependance ou detecter l'outil manquant dans code doctor.",
        "module_not_found": "Verifier requirements/pyproject avant de proposer une installation locale.",
        "test_failure": "Creer un patch plan minimal depuis le premier test en echec.",
        "permission_denied": "Verifier workspace policy et chemins relatifs.",
        "git_not_repository": "Scanner le workspace et clarifier si un depot git est attendu.",
        "tool_denied": "Examiner la policy qui refuse le tool et confirmer si le refus est attendu.",
    }
    return mapping.get(failure_type, "Examiner les traces redacted et ajouter un test de regression cible.")
