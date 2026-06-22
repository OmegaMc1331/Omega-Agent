from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.evals.failure_clustering import FailureClustering
from omega_agent.evals.metrics import MetricsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


class EvalReports:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def build_report(self) -> dict:
        metrics = MetricsStore(self.config)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics.aggregate_metrics(days=7),
            "models": metrics.model_performance_summary(),
            "tools": metrics.tool_reliability_summary(),
            "agents": metrics.agent_profile_performance_summary(),
            "policy": metrics.policy_friction_summary(),
            "failures": FailureClustering(self.config).cluster_recent_failures(limit=100),
        }
        return redact(report)

    def write_report(self) -> Path:
        report = self.build_report()
        report_dir = self.config.evals_report_dir or (Path.home() / ".omega" / "eval_reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"omega-eval-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def list_reports(self) -> list[dict]:
        report_dir = self.config.evals_report_dir or (Path.home() / ".omega" / "eval_reports")
        if not report_dir.exists():
            return []
        return [
            {"name": path.name, "path": str(path), "size": path.stat().st_size, "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
            for path in sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        ]
