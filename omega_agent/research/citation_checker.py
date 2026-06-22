from __future__ import annotations

import re

from omega_agent.research.confidence import score_claim_confidence, status_for_confidence
from omega_agent.research.evidence_graph import ResearchClaim, ResearchEvidence, ResearchRepository, ResearchSource


class CitationChecker:
    def __init__(self, repository: ResearchRepository):
        self.repository = repository

    def verify_claim_has_evidence(self, claim: ResearchClaim) -> bool:
        evidence = self.repository.list_evidence(claim.research_run_id, claim_id=claim.id)
        return any(item.source_id and item.quote for item in evidence)

    def detect_weak_citation(
        self,
        claim: ResearchClaim,
        evidence: list[ResearchEvidence],
        sources: dict[str, ResearchSource],
    ) -> bool:
        if not evidence:
            return True
        if not any(item.quote and item.relevance_score >= 0.7 for item in evidence):
            return True
        return all(sources.get(item.source_id) is None or sources[item.source_id].trust_level in {"external", "untrusted"} for item in evidence)

    def detect_contradictions(self, claims: list[ResearchClaim]) -> set[str]:
        contradicted: set[str] = set()
        for index, left in enumerate(claims):
            for right in claims[index + 1 :]:
                if _contradictory(left.claim_text, right.claim_text):
                    contradicted.update({left.id, right.id})
        return contradicted

    def require_citation_for_factual_claim(self, claim: ResearchClaim) -> bool:
        return str(claim.metadata.get("claim_type") or "factual") == "factual"

    def verify_run(self, research_run_id: str) -> list[ResearchClaim]:
        claims = self.repository.list_claims(research_run_id)
        sources = {source.id: source for source in self.repository.list_sources(research_run_id)}
        contradicted_ids = self.detect_contradictions(claims)
        verified: list[ResearchClaim] = []
        for claim in claims:
            evidence = self.repository.list_evidence(research_run_id, claim_id=claim.id)
            contradicted = claim.id in contradicted_ids or any(item.supports is False for item in evidence)
            has_evidence = bool(evidence)
            confidence = score_claim_confidence(evidence, sources, contradiction_present=contradicted)
            status = status_for_confidence(confidence, has_evidence=has_evidence, contradicted=contradicted)
            if self.require_citation_for_factual_claim(claim) and not any(item.quote for item in evidence):
                confidence = 0.0
                status = "unsupported"
            metadata = {
                **claim.metadata,
                "citation_checked": True,
                "weak_citation": self.detect_weak_citation(claim, evidence, sources),
                "evidence_count": len(evidence),
            }
            verified.append(self.repository.update_claim(claim.id, confidence=confidence, status=status, metadata=metadata))
        return verified


def _contradictory(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    if overlap < 0.65:
        return False
    return _has_negation(left) != _has_negation(right)


def _tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "that", "this", "une", "des", "les", "dans", "pour", "avec", "est", "sont"}
    return {token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", value.lower()) if len(token) > 2 and token not in stop}


def _has_negation(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in (" not ", " no ", " never ", " n'est ", " ne ", " sans ", " aucun"))
