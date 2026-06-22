from __future__ import annotations

from omega_agent.research.evidence_graph import ResearchClaim, ResearchEvidence, ResearchRun, ResearchSource, confidence_summary


class ReportBuilder:
    def build_markdown(
        self,
        run: ResearchRun,
        sources: list[ResearchSource],
        claims: list[ResearchClaim],
        evidence: list[ResearchEvidence],
    ) -> str:
        source_labels = {source.id: f"S{index}" for index, source in enumerate(sources, start=1)}
        evidence_by_claim: dict[str, list[ResearchEvidence]] = {}
        for item in evidence:
            evidence_by_claim.setdefault(item.claim_id, []).append(item)
        supported = [claim for claim in claims if claim.status == "supported"]
        uncertain = [claim for claim in claims if claim.status != "supported"]
        summary = confidence_summary(claims)
        lines = [
            f"# {run.title}",
            "",
            "## Question",
            "",
            run.question,
            "",
            "## Méthode",
            "",
            "Recherche locale bornée, collecte read-only, extraction de claims, liaison aux preuves, contrôle des citations et notation de confiance.",
            "Les contenus externes sont traités comme non fiables et leurs instructions éventuelles sont ignorées.",
            "",
            "## Synthèse",
            "",
        ]
        if supported:
            lines.extend(f"- {claim.claim_text} ({_citations(evidence_by_claim.get(claim.id, []), source_labels)})" for claim in supported[:8])
        else:
            lines.append("La preuve disponible est insuffisante pour produire une conclusion soutenue.")
        lines.extend(
            [
                "",
                "## Findings",
                "",
                "| Claim | Statut | Confiance | Preuves |",
                "|---|---:|---:|---|",
            ]
        )
        for claim in claims:
            refs = _citations(evidence_by_claim.get(claim.id, []), source_labels)
            lines.append(f"| {_cell(claim.claim_text)} | {claim.status} | {claim.confidence:.0%} | {refs or 'Aucune preuve'} |")
        if not claims:
            lines.append("| Aucun claim extrait | unsupported | 0% | Aucune preuve |")
        lines.extend(["", "## Claims et preuves", ""])
        for claim in claims:
            lines.append(f"### {claim.status.upper()} · {claim.confidence:.0%}")
            lines.append("")
            lines.append(claim.claim_text)
            lines.append("")
            linked = evidence_by_claim.get(claim.id, [])
            if not linked:
                lines.append("- Preuve insuffisante : aucune citation vérifiable.")
            for item in linked:
                label = source_labels.get(item.source_id, "source inconnue")
                relation = "soutient" if item.supports is True else "contredit" if item.supports is False else "mentionne"
                quote = f' — « {item.quote} »' if item.quote else ""
                lines.append(f"- [{label}] {relation} le claim (pertinence {item.relevance_score:.0%}){quote}")
            lines.append("")
        lines.extend(["## Incertitudes", ""])
        if uncertain:
            for claim in uncertain:
                lines.append(f"- {claim.status}: {claim.claim_text}")
        else:
            lines.append("- Aucune contradiction détectée, mais l'absence de contradiction ne prouve pas l'exhaustivité.")
        lines.extend(["", "## Sources", ""])
        for source in sources:
            label = source_labels[source.id]
            locator = _source_locator(source)
            lines.append(f"- [{label}] {source.title} — `{locator}` — confiance source: {source.trust_level}")
        if not sources:
            lines.append("- Aucune source fiable collectée.")
        lines.extend(
            [
                "",
                "## Limites",
                "",
                "- L'extraction v1 est déterministe et peut manquer des formulations implicites.",
                "- Une source unique ne garantit pas l'indépendance de la preuve.",
                "- Les contenus externes et manuels peuvent être inexacts ou malveillants.",
                "- Aucune URL ni citation n'est ajoutée sans source collectée.",
                f"- Confiance moyenne du rapport: {summary['average']:.0%} sur {summary['total']} claim(s).",
                "",
                "## Prochaines actions",
                "",
                "- Ajouter des sources indépendantes pour les claims faibles ou non soutenus.",
                "- Vérifier manuellement les contradictions et la fraîcheur des sources importantes.",
                "- Relancer la recherche avec un connecteur web read-only configuré si la preuve locale est insuffisante.",
                "",
            ]
        )
        return "\n".join(lines)


def _citations(evidence: list[ResearchEvidence], labels: dict[str, str]) -> str:
    refs = []
    for item in evidence:
        label = labels.get(item.source_id)
        if label and item.quote and label not in refs:
            refs.append(label)
    return " ".join(f"[{label}]" for label in refs)


def _source_locator(source: ResearchSource) -> str:
    if source.source_type == "file":
        return source.locator or "workspace file"
    if source.source_type == "memory":
        return source.locator or f"memory:{source.id}"
    if source.source_type in {"connector", "web"}:
        return source.locator or str(source.metadata.get("connector_id") or "connector")
    return source.locator or "manual source"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
