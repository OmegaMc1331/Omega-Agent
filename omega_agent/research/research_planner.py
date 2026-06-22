from __future__ import annotations

import re

from omega_agent.config import OmegaConfig
from omega_agent.connectors.registry import ConnectorsRegistry


class ResearchPlanner:
    def __init__(self, config: OmegaConfig):
        self.config = config

    def create_research_plan(self, question: str) -> dict:
        return {
            "question": " ".join(question.split()),
            "scope": self.estimate_research_scope(question),
            "needed_sources": self.identify_needed_sources(question),
            "capabilities": self.select_capabilities_for_research(question),
            "steps": [
                "Clarifier la question et les critères de preuve.",
                "Collecter des sources locales et connecteurs read-only disponibles.",
                "Extraire les claims et relier chaque claim à des preuves directes.",
                "Vérifier citations, contradictions et confiance.",
                "Produire un rapport avec incertitudes et limites.",
            ],
            "constraints": {
                "max_sources": self.config.research_max_sources,
                "max_claims": self.config.research_max_claims,
                "web_enabled": self.config.research_web_enabled,
                "external_sources_untrusted": self.config.research_external_sources_untrusted,
                "browser_allowed": False,
                "shell_allowed": False,
            },
        }

    def identify_needed_sources(self, question: str) -> list[dict]:
        sources = [
            {"type": "file", "reason": "Priorité aux fichiers du workspace, avec chemin relatif comme citation."},
            {"type": "memory", "reason": "Réutiliser les connaissances locales seulement avec provenance."},
        ]
        connector_count = sum(
            1
            for connector in ConnectorsRegistry(self.config).list()
            if connector.enabled and connector.status == "available" and any(operation.action_category == "read_only" for operation in connector.operations)
        )
        if connector_count:
            sources.append({"type": "connector", "reason": f"{connector_count} connecteur(s) read-only disponible(s)."})
        if self.config.research_web_enabled:
            sources.append({"type": "web", "reason": "Recherche web autorisée uniquement via connecteur configuré."})
        return sources

    def select_capabilities_for_research(self, question: str) -> list[str]:
        capabilities = ["read_file", "list_files", "search_memory"]
        if self.config.connectors_enabled:
            capabilities.append("connectors:read_only")
        if self.config.research_web_enabled:
            capabilities.append("web_search_connector")
        return capabilities

    def estimate_research_scope(self, question: str) -> dict:
        words = re.findall(r"\w+", question)
        comparative = any(token in question.lower() for token in ("compare", "compar", "versus", "vs", "options", "alternatives"))
        level = "large" if len(words) > 35 or comparative else "medium" if len(words) > 14 else "small"
        source_target = {"small": 6, "medium": 12, "large": 20}[level]
        return {"level": level, "target_sources": min(source_target, self.config.research_max_sources)}
