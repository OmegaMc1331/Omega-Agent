from __future__ import annotations

import re
from dataclasses import dataclass

from omega_agent.research.evidence_graph import ResearchSource


@dataclass(frozen=True)
class ExtractedClaim:
    text: str
    claim_type: str
    source_id: str
    quote: str
    relevance_score: float


class ClaimExtractor:
    def __init__(self, max_claims: int = 50):
        self.max_claims = max(1, max_claims)

    def extract_claims(self, draft_or_sources) -> list[ExtractedClaim]:
        sources = draft_or_sources if isinstance(draft_or_sources, list) else []
        claims: list[ExtractedClaim] = []
        seen: set[str] = set()
        for source in sources:
            if not isinstance(source, ResearchSource) or not source.content_excerpt:
                continue
            for raw in _candidate_sentences(source.content_excerpt):
                normalized = self.normalize_claim(raw)
                key = normalized.lower()
                if not normalized or key in seen:
                    continue
                seen.add(key)
                claims.append(
                    ExtractedClaim(
                        text=normalized,
                        claim_type=self.detect_claim_type(normalized),
                        source_id=source.id,
                        quote=raw.strip()[:2000],
                        relevance_score=_relevance(normalized),
                    )
                )
                if len(claims) >= self.max_claims:
                    return claims
        return claims

    def normalize_claim(self, claim: str) -> str:
        value = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(claim or ""))
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) < 18 or len(value) > 700:
            return ""
        return value.rstrip()

    def detect_claim_type(self, claim: str) -> str:
        lowered = claim.lower()
        if re.search(r"\b(def|class|function|return|import|const|let|var)\b|[{};]|=>", claim):
            return "code"
        if any(token in lowered for token in ("devrait", "should", "recommend", "recommande", "il faut", "préférer")):
            return "recommendation"
        if any(token in lowered for token in ("environ", "estimate", "estimé", "approx", "~")):
            return "estimate"
        if any(token in lowered for token in ("je pense", "opinion", "selon nous", "we believe")):
            return "opinion"
        if lowered.startswith(("résumé", "summary", "ce document", "this document")):
            return "source_summary"
        return "factual"


def _candidate_sentences(content: str) -> list[str]:
    candidates: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "```", "<", "{", "}")):
            continue
        if len(stripped) <= 700 and (stripped.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]\s", stripped)):
            candidates.append(stripped)
            continue
        candidates.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", stripped) if part.strip())
    return candidates


def _relevance(claim: str) -> float:
    score = 0.75
    if re.search(r"\d", claim):
        score += 0.1
    if len(claim.split()) >= 8:
        score += 0.05
    return min(score, 0.95)
