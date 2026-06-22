from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact


@dataclass(frozen=True)
class ResearchRun:
    id: str
    session_id: str | None
    run_id: str | None
    title: str
    question: str
    status: str
    plan: dict[str, Any]
    report_markdown: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class ResearchSource:
    id: str
    research_run_id: str
    source_type: str
    title: str
    uri: str | None
    locator: str | None
    content_excerpt: str | None
    trust_level: str
    collected_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class ResearchClaim:
    id: str
    research_run_id: str
    claim_text: str
    confidence: float
    status: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class ResearchEvidence:
    id: str
    research_run_id: str
    claim_id: str
    source_id: str
    quote: str | None
    relevance_score: float
    supports: bool | None
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


@dataclass(frozen=True)
class ResearchReport:
    id: str
    research_run_id: str
    format: str
    content: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        return redact(asdict(self))


class ResearchRepository:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def create_run(
        self,
        question: str,
        *,
        title: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchRun:
        now = _now()
        research_run_id = uuid4().hex
        clean_question = " ".join(str(question or "").split())
        clean_title = " ".join(str(title or clean_question).split())[:160] or "Research"
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO research_runs(
                    id, session_id, run_id, title, question, status, plan_json,
                    report_markdown, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, 'pending', '{}', NULL, ?, ?, ?)
                """,
                (
                    research_run_id,
                    session_id,
                    run_id,
                    clean_title,
                    clean_question,
                    now,
                    now,
                    _json(redact(metadata or {})),
                ),
            )
        return self.require_run(research_run_id)

    def list_runs(self, *, status: str | None = None, limit: int = 100) -> list[ResearchRun]:
        query = "SELECT * FROM research_runs"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_run(row) for row in rows]

    def get_run(self, research_run_id: str) -> ResearchRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM research_runs WHERE id = ?", (research_run_id,)).fetchone()
        return _run(row) if row else None

    def require_run(self, research_run_id: str) -> ResearchRun:
        run = self.get_run(research_run_id)
        if run is None:
            raise ValueError("Research run introuvable.")
        return run

    def update_run(
        self,
        research_run_id: str,
        *,
        status: str | None = None,
        plan: dict[str, Any] | None = None,
        report_markdown: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchRun:
        current = self.require_run(research_run_id)
        values = {
            "status": status or current.status,
            "plan_json": _json(redact(plan if plan is not None else current.plan)),
            "report_markdown": redact(report_markdown) if report_markdown is not None else current.report_markdown,
            "metadata_json": _json(redact(metadata if metadata is not None else current.metadata)),
            "updated_at": _now(),
        }
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE research_runs
                SET status = ?, plan_json = ?, report_markdown = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["status"],
                    values["plan_json"],
                    values["report_markdown"],
                    values["metadata_json"],
                    values["updated_at"],
                    research_run_id,
                ),
            )
        return self.require_run(research_run_id)

    def cancel_run(self, research_run_id: str) -> ResearchRun:
        current = self.require_run(research_run_id)
        if current.status in {"succeeded", "failed", "cancelled"}:
            return current
        return self.update_run(research_run_id, status="cancelled")

    def add_source(
        self,
        research_run_id: str,
        *,
        source_type: str,
        title: str,
        uri: str | None = None,
        locator: str | None = None,
        content_excerpt: str | None = None,
        trust_level: str = "untrusted",
        metadata: dict[str, Any] | None = None,
    ) -> ResearchSource:
        source_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO research_sources(
                    id, research_run_id, source_type, title, uri, locator,
                    content_excerpt, trust_level, collected_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    research_run_id,
                    source_type,
                    redact(title)[:500],
                    redact(uri) if uri else None,
                    redact(locator) if locator else None,
                    redact(content_excerpt)[:20000] if content_excerpt else None,
                    trust_level,
                    now,
                    _json(redact(metadata or {})),
                ),
            )
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> ResearchSource:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM research_sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise ValueError("Source introuvable.")
        return _source(row)

    def list_sources(self, research_run_id: str) -> list[ResearchSource]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM research_sources WHERE research_run_id = ? ORDER BY collected_at ASC",
                (research_run_id,),
            ).fetchall()
        return [_source(row) for row in rows]

    def add_claim(
        self,
        research_run_id: str,
        claim_text: str,
        *,
        confidence: float = 0.0,
        status: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> ResearchClaim:
        claim_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO research_claims(
                    id, research_run_id, claim_text, confidence, status, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    research_run_id,
                    redact(claim_text)[:4000],
                    max(0.0, min(float(confidence), 1.0)),
                    status,
                    now,
                    _json(redact(metadata or {})),
                ),
            )
        return self.get_claim(claim_id)

    def get_claim(self, claim_id: str) -> ResearchClaim:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM research_claims WHERE id = ?", (claim_id,)).fetchone()
        if row is None:
            raise ValueError("Claim introuvable.")
        return _claim(row)

    def update_claim(self, claim_id: str, *, confidence: float, status: str, metadata: dict[str, Any] | None = None) -> ResearchClaim:
        current = self.get_claim(claim_id)
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE research_claims SET confidence = ?, status = ?, metadata_json = ? WHERE id = ?",
                (
                    max(0.0, min(float(confidence), 1.0)),
                    status,
                    _json(redact(metadata if metadata is not None else current.metadata)),
                    claim_id,
                ),
            )
        return self.get_claim(claim_id)

    def list_claims(self, research_run_id: str) -> list[ResearchClaim]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM research_claims WHERE research_run_id = ? ORDER BY created_at ASC",
                (research_run_id,),
            ).fetchall()
        return [_claim(row) for row in rows]

    def add_evidence(
        self,
        research_run_id: str,
        claim_id: str,
        source_id: str,
        *,
        quote: str | None = None,
        relevance_score: float = 0.0,
        supports: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchEvidence:
        evidence_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO research_evidence(
                    id, research_run_id, claim_id, source_id, quote, relevance_score,
                    supports, created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    research_run_id,
                    claim_id,
                    source_id,
                    redact(quote)[:8000] if quote else None,
                    max(0.0, min(float(relevance_score), 1.0)),
                    None if supports is None else int(bool(supports)),
                    now,
                    _json(redact(metadata or {})),
                ),
            )
        return self.get_evidence(evidence_id)

    def get_evidence(self, evidence_id: str) -> ResearchEvidence:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM research_evidence WHERE id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise ValueError("Evidence introuvable.")
        return _evidence(row)

    def list_evidence(self, research_run_id: str, *, claim_id: str | None = None) -> list[ResearchEvidence]:
        query = "SELECT * FROM research_evidence WHERE research_run_id = ?"
        params: list[Any] = [research_run_id]
        if claim_id:
            query += " AND claim_id = ?"
            params.append(claim_id)
        query += " ORDER BY created_at ASC"
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_evidence(row) for row in rows]

    def add_report(
        self,
        research_run_id: str,
        *,
        format: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchReport:
        report_id = uuid4().hex
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO research_reports(id, research_run_id, format, content, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (report_id, research_run_id, format, redact(content), now, _json(redact(metadata or {}))),
            )
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> ResearchReport:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM research_reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            raise ValueError("Rapport introuvable.")
        return _report(row)

    def list_reports(self, research_run_id: str) -> list[ResearchReport]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM research_reports WHERE research_run_id = ? ORDER BY created_at DESC",
                (research_run_id,),
            ).fetchall()
        return [_report(row) for row in rows]

    def graph(self, research_run_id: str) -> dict[str, Any]:
        sources = self.list_sources(research_run_id)
        claims = self.list_claims(research_run_id)
        evidence = self.list_evidence(research_run_id)
        nodes = [
            {
                "id": f"source:{source.id}",
                "node_type": "source",
                "label": source.title,
                "trust_level": source.trust_level,
                "source_type": source.source_type,
            }
            for source in sources
        ]
        nodes.extend(
            {
                "id": f"claim:{claim.id}",
                "node_type": "claim",
                "label": claim.claim_text,
                "status": claim.status,
                "confidence": claim.confidence,
            }
            for claim in claims
        )
        edges = [
            {
                "id": item.id,
                "source": f"source:{item.source_id}",
                "target": f"claim:{item.claim_id}",
                "type": "supports" if item.supports is True else "contradicts" if item.supports is False else "mentions",
                "relevance_score": item.relevance_score,
                "quote": item.quote,
            }
            for item in evidence
        ]
        return {
            "research_run_id": research_run_id,
            "nodes": nodes,
            "edges": edges,
            "confidence_summary": confidence_summary(claims),
        }


def confidence_summary(claims: list[ResearchClaim]) -> dict[str, Any]:
    counts = {status: 0 for status in ("supported", "weak", "contradicted", "unsupported", "unknown")}
    for claim in claims:
        counts[claim.status] = counts.get(claim.status, 0) + 1
    average = sum(claim.confidence for claim in claims) / len(claims) if claims else 0.0
    return {"average": round(average, 3), "total": len(claims), "status_counts": counts}


def _run(row) -> ResearchRun:
    return ResearchRun(
        id=row["id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        title=row["title"],
        question=row["question"],
        status=row["status"],
        plan=_dict(row["plan_json"]),
        report_markdown=row["report_markdown"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_dict(row["metadata_json"]),
    )


def _source(row) -> ResearchSource:
    return ResearchSource(
        id=row["id"],
        research_run_id=row["research_run_id"],
        source_type=row["source_type"],
        title=row["title"],
        uri=row["uri"],
        locator=row["locator"],
        content_excerpt=row["content_excerpt"],
        trust_level=row["trust_level"],
        collected_at=row["collected_at"],
        metadata=_dict(row["metadata_json"]),
    )


def _claim(row) -> ResearchClaim:
    return ResearchClaim(
        id=row["id"],
        research_run_id=row["research_run_id"],
        claim_text=row["claim_text"],
        confidence=float(row["confidence"]),
        status=row["status"],
        created_at=row["created_at"],
        metadata=_dict(row["metadata_json"]),
    )


def _evidence(row) -> ResearchEvidence:
    raw_supports = row["supports"]
    return ResearchEvidence(
        id=row["id"],
        research_run_id=row["research_run_id"],
        claim_id=row["claim_id"],
        source_id=row["source_id"],
        quote=row["quote"],
        relevance_score=float(row["relevance_score"]),
        supports=None if raw_supports is None else bool(raw_supports),
        created_at=row["created_at"],
        metadata=_dict(row["metadata_json"]),
    )


def _report(row) -> ResearchReport:
    return ResearchReport(
        id=row["id"],
        research_run_id=row["research_run_id"],
        format=row["format"],
        content=row["content"],
        created_at=row["created_at"],
        metadata=_dict(row["metadata_json"]),
    )


def _dict(value: str | None) -> dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
