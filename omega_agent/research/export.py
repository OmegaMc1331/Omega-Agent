from __future__ import annotations

import json
import re
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.research.evidence_graph import ResearchRepository
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.security.redaction import redact
from omega_agent.security.sandbox import is_path_inside_workspace, safe_path


class ResearchExporter:
    def __init__(self, config: OmegaConfig, repository: ResearchRepository):
        self.config = config
        self.repository = repository

    def export(self, research_run_id: str, format: str = "markdown") -> dict:
        normalized = "markdown" if format in {"md", "markdown"} else "json" if format == "json" else ""
        if not normalized:
            raise ValueError("Format export invalide: markdown ou json.")
        run = self.repository.require_run(research_run_id)
        export_root = safe_path(self.config, self.config.research_export_dir)
        if not is_path_inside_workspace(export_root, self.config.workspace):
            raise PermissionError("Export refuse: dossier hors workspace.")
        export_root.mkdir(parents=True, exist_ok=True)
        stem = _slug(run.title)[:72] or "research"
        suffix = ".md" if normalized == "markdown" else ".json"
        target = safe_path(self.config, str(Path(self.config.research_export_dir) / f"{stem}-{run.id[:8]}{suffix}"))
        if run.run_id:
            DurableRuntime(self.config).create_snapshot_for_paths(run.run_id, None, [target])
        if normalized == "markdown":
            content = run.report_markdown or ""
            if not content:
                raise ValueError("Rapport Markdown indisponible.")
        else:
            content = json.dumps(
                redact(
                    {
                        "run": run.as_api(),
                        "sources": [item.as_api() for item in self.repository.list_sources(run.id)],
                        "claims": [item.as_api() for item in self.repository.list_claims(run.id)],
                        "evidence": [item.as_api() for item in self.repository.list_evidence(run.id)],
                        "graph": self.repository.graph(run.id),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        target.write_text(content, encoding="utf-8")
        report = self.repository.add_report(
            run.id,
            format=normalized,
            content=content,
            metadata={"workspace_path": target.relative_to(self.config.workspace.resolve()).as_posix()},
        )
        return {
            "report": report.as_api(),
            "path": target.relative_to(self.config.workspace.resolve()).as_posix(),
            "format": normalized,
        }


def _slug(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return lowered
