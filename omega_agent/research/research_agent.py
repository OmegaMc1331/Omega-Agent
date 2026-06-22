from __future__ import annotations

from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.research.citation_checker import CitationChecker
from omega_agent.research.claim_extractor import ClaimExtractor
from omega_agent.research.evidence_graph import ResearchRepository, ResearchRun
from omega_agent.research.export import ResearchExporter
from omega_agent.research.report_builder import ReportBuilder
from omega_agent.research.research_planner import ResearchPlanner
from omega_agent.research.source_collector import CollectedSource, SourceCollector
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.security.redaction import redact


class OmegaResearchAgent:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.repository = ResearchRepository(config)
        self.events = EventsStore(config)
        self.planner = ResearchPlanner(config)
        self.collector = SourceCollector(config)
        self.extractor = ClaimExtractor(config.research_max_claims)
        self.checker = CitationChecker(self.repository)
        self.report_builder = ReportBuilder()
        self.exporter = ResearchExporter(config, self.repository)

    def start(
        self,
        question: str,
        *,
        title: str | None = None,
        session_id: str | None = None,
        manual_sources: list[dict[str, Any]] | None = None,
    ) -> ResearchRun:
        if not self.config.research_enabled:
            raise PermissionError("Omega Research est désactivé par configuration.")
        clean_question = " ".join(str(question or "").split())
        if not clean_question:
            raise ValueError("Question de recherche requise.")
        sessions = SessionsStore(self.config)
        if session_id:
            session = sessions.get_session(session_id)
            if session is None:
                raise ValueError("Session introuvable.")
        else:
            session = sessions.create_session(f"Research: {clean_question[:80]}")
            sessions.set_agent_profile(session.id, "omega-research")
        durable = DurableRuntime(self.config)
        durable_run = durable.create_run(
            session.id,
            clean_question,
            metadata={"active_agent_profile_id": "omega-research", "kind": "research"},
        )
        durable.start_run(durable_run.id)
        run = self.repository.create_run(
            clean_question,
            title=title,
            session_id=session.id,
            run_id=durable_run.id,
            metadata={"agent_profile_id": "omega-research"},
        )
        self._emit("research.started", run, {"question": clean_question})
        try:
            run = self._plan(run, durable)
            run = self._collect(run, durable, manual_sources)
            run = self._analyze(run, durable)
            run = self._report(run, durable)
            run = self.repository.update_run(run.id, status="succeeded")
            durable.complete_run(durable_run.id, run.report_markdown or "Research completed.")
            self._emit("research.completed", run, {"status": "succeeded"})
            return run
        except Exception as exc:
            failed = self.repository.update_run(
                run.id,
                status="failed",
                metadata={**run.metadata, "error": redact(str(exc))},
            )
            durable.fail_run(durable_run.id, str(exc))
            self._emit("research.failed", failed, {"error": redact(str(exc))})
            raise

    def cancel(self, research_run_id: str) -> ResearchRun:
        run = self.repository.cancel_run(research_run_id)
        if run.run_id:
            DurableRuntime(self.config).cancel_run(run.run_id)
        self._emit("research.completed", run, {"status": "cancelled"})
        return run

    def export(self, research_run_id: str, format: str = "markdown") -> dict:
        return self.exporter.export(research_run_id, format=format)

    def detail(self, research_run_id: str) -> dict[str, Any]:
        run = self.repository.require_run(research_run_id)
        return {
            **run.as_api(),
            "sources": [item.as_api() for item in self.repository.list_sources(run.id)],
            "claims": [item.as_api() for item in self.repository.list_claims(run.id)],
            "evidence": [item.as_api() for item in self.repository.list_evidence(run.id)],
            "reports": [item.as_api() for item in self.repository.list_reports(run.id)],
            "graph": self.repository.graph(run.id),
        }

    def _plan(self, run: ResearchRun, durable: DurableRuntime) -> ResearchRun:
        run = self.repository.update_run(run.id, status="planning")
        step = durable.append_step(run.run_id, "reasoning", "Research planning", status="running")
        plan = self.planner.create_research_plan(run.question)
        run = self.repository.update_run(run.id, plan=plan)
        durable.complete_step(step.id, {"plan": plan})
        self._emit("research.plan.created", run, {"plan": plan})
        return run

    def _collect(
        self,
        run: ResearchRun,
        durable: DurableRuntime,
        manual_sources: list[dict[str, Any]] | None,
    ) -> ResearchRun:
        run = self.repository.update_run(run.id, status="collecting")
        step = durable.append_step(run.run_id, "tool_call", "Collect research sources", status="running")
        candidates: list[CollectedSource] = []
        candidates.extend(self.collector.collect_from_workspace_files(run.question))
        candidates.extend(self.collector.collect_from_memory(run.question))
        candidates.extend(self.collector.collect_from_connectors(run.question))
        candidates.extend(self.collector.collect_from_manual_sources(manual_sources))
        seen: set[tuple[str, str]] = set()
        persisted = 0
        for candidate in candidates:
            key = (candidate.source_type, candidate.locator or candidate.title)
            if key in seen or persisted >= self.config.research_max_sources:
                continue
            seen.add(key)
            source = self.repository.add_source(
                run.id,
                source_type=candidate.source_type,
                title=candidate.title,
                uri=candidate.uri,
                locator=candidate.locator,
                content_excerpt=candidate.content,
                trust_level=candidate.trust_level,
                metadata={**candidate.metadata, "external_content_untrusted": candidate.trust_level == "untrusted"},
            )
            persisted += 1
            self._emit(
                "research.source.collected",
                run,
                {"source_id": source.id, "source_type": source.source_type, "title": source.title, "trust_level": source.trust_level},
            )
        durable.complete_step(step.id, {"sources_collected": persisted})
        return run

    def _analyze(self, run: ResearchRun, durable: DurableRuntime) -> ResearchRun:
        run = self.repository.update_run(run.id, status="analyzing")
        step = durable.append_step(run.run_id, "reasoning", "Extract and verify claims", status="running")
        sources = self.repository.list_sources(run.id)
        extracted = self.extractor.extract_claims(sources)
        for item in extracted:
            claim = self.repository.add_claim(
                run.id,
                item.text,
                metadata={"claim_type": item.claim_type, "source_derived": True},
            )
            self._emit(
                "research.claim.extracted",
                run,
                {"claim_id": claim.id, "claim_type": item.claim_type, "claim_text": claim.claim_text},
            )
            evidence = self.repository.add_evidence(
                run.id,
                claim.id,
                item.source_id,
                quote=item.quote,
                relevance_score=item.relevance_score,
                supports=True,
                metadata={"direct_quote_match": True},
            )
            self._emit(
                "research.evidence.linked",
                run,
                {"evidence_id": evidence.id, "claim_id": claim.id, "source_id": item.source_id, "supports": True},
            )
        verified = self.checker.verify_run(run.id)
        for claim in verified:
            self._emit(
                "research.claim.verified",
                run,
                {"claim_id": claim.id, "status": claim.status, "confidence": claim.confidence},
            )
        durable.complete_step(step.id, {"claims": len(verified)})
        return run

    def _report(self, run: ResearchRun, durable: DurableRuntime) -> ResearchRun:
        run = self.repository.update_run(run.id, status="reporting")
        step = durable.append_step(run.run_id, "final_response", "Build research report", status="running")
        report = self.report_builder.build_markdown(
            run,
            self.repository.list_sources(run.id),
            self.repository.list_claims(run.id),
            self.repository.list_evidence(run.id),
        )
        run = self.repository.update_run(run.id, report_markdown=report)
        record = self.repository.add_report(run.id, format="markdown", content=report, metadata={"generated": True})
        durable.complete_step(step.id, {"report_id": record.id})
        self._emit("research.report.created", run, {"report_id": record.id, "format": "markdown"})
        return run

    def _emit(self, event_type: str, run: ResearchRun, payload: dict[str, Any]) -> None:
        self.events.add(
            event_type,
            {"research_run_id": run.id, "run_id": run.run_id, **redact(payload)},
            session_id=run.session_id,
        )
