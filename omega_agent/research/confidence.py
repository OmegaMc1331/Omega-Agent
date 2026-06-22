from __future__ import annotations

from datetime import datetime, timezone

from omega_agent.research.evidence_graph import ResearchEvidence, ResearchSource

TRUST_SCORES = {
    "trusted": 0.9,
    "local": 0.78,
    "external": 0.52,
    "untrusted": 0.32,
}


def score_claim_confidence(
    evidence: list[ResearchEvidence],
    sources: dict[str, ResearchSource],
    *,
    contradiction_present: bool = False,
) -> float:
    if not evidence:
        return 0.0
    linked_sources = [sources[item.source_id] for item in evidence if item.source_id in sources]
    if not linked_sources:
        return 0.0
    trust = sum(TRUST_SCORES.get(source.trust_level, 0.25) for source in linked_sources) / len(linked_sources)
    independent = len({(source.source_type, source.locator or source.uri or source.id) for source in linked_sources})
    independent_bonus = min(0.16, max(0, independent - 1) * 0.08)
    quote_bonus = 0.14 if any(item.quote and item.relevance_score >= 0.7 for item in evidence) else 0.0
    local_bonus = 0.04 if any(source.source_type in {"file", "memory"} for source in linked_sources) else 0.0
    freshness_bonus = 0.0
    for source in linked_sources:
        if _is_fresh(source.metadata.get("published_at") or source.metadata.get("updated_at")):
            freshness_bonus = 0.04
            break
    contradiction_penalty = 0.48 if contradiction_present or any(item.supports is False for item in evidence) else 0.0
    return round(max(0.0, min(1.0, trust + independent_bonus + quote_bonus + local_bonus + freshness_bonus - contradiction_penalty)), 3)


def status_for_confidence(confidence: float, *, has_evidence: bool, contradicted: bool = False) -> str:
    if contradicted:
        return "contradicted"
    if not has_evidence:
        return "unsupported"
    return "supported" if confidence >= 0.7 else "weak"


def _is_fresh(value) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).days <= 365
