from __future__ import annotations

from dataclasses import asdict, dataclass

from omega_agent.config import OmegaConfig
from omega_agent.governance.budget_enforcer import BudgetEnforcer
from omega_agent.runtime.error_taxonomy import ClassifiedError, classify_error
from omega_agent.runtime.events import EventsStore


@dataclass(frozen=True)
class RecoverySuggestion:
    kind: str
    message: str
    safe_to_auto_apply: bool = False
    commands: list[str] | None = None

    def as_api(self) -> dict:
        return asdict(self)


class SelfHealingEngine:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        self.budgets = BudgetEnforcer(config)

    def classify_error(self, error_text: str, context: dict | None = None) -> ClassifiedError:
        classified = classify_error(error_text, context)
        self.events.add("error.classified", classified.as_api(), session_id=(context or {}).get("session_id"))
        return classified

    def suggest_recovery(self, error_type: str, context: dict | None = None) -> RecoverySuggestion:
        suggestion = suggest_recovery_for_type(error_type, context or {}, self.config)
        self.events.add("self_healing.suggested", suggestion.as_api(), session_id=(context or {}).get("session_id"))
        return suggestion

    def can_auto_recover(self, error_type: str, context: dict | None = None) -> bool:
        if not self.config.self_healing_enabled or not self.config.self_healing_auto_apply_safe_recoveries:
            return False
        if self.attempts_for_run((context or {}).get("run_id")) >= self.config.self_healing_max_attempts:
            return False
        budget_context = self.budgets.context(run_id=(context or {}).get("run_id"), session_id=(context or {}).get("session_id"))
        if self.budgets.check_metric(budget_context, "max_retries").action in {"pause", "deny", "require_approval"}:
            return False
        return error_type in {"json_decode_error"}

    def attempt_recovery(self, error_type: str, context: dict | None = None) -> dict:
        context = context or {}
        if self.attempts_for_run(context.get("run_id")) >= self.config.self_healing_max_attempts:
            return {"status": "skipped", "reason": "max_attempts_reached", "suggestion": self.suggest_recovery(error_type, context).as_api()}
        budget_context = self.budgets.context(run_id=context.get("run_id"), session_id=context.get("session_id"))
        budget_decision = self.budgets.check_metric(budget_context, "max_retries")
        if budget_decision.action in {"pause", "deny", "require_approval"}:
            return {"status": "skipped", "reason": "budget_exceeded", "budget_decision": budget_decision.as_api(), "suggestion": self.suggest_recovery(error_type, context).as_api()}
        suggestion = self.suggest_recovery(error_type, context)
        if not self.can_auto_recover(error_type, context):
            return {"status": "suggested", "suggestion": suggestion.as_api()}
        self.events.add("self_healing.started", {"run_id": context.get("run_id"), "error_type": error_type}, session_id=context.get("session_id"))
        self.budgets.record_usage(budget_context, "max_retries", 1, metadata={"error_type": error_type, "source": "self_healing"})
        result = {"status": "completed", "error_type": error_type, "message": "Recovery safe v1: suggestion recorded; no risky action executed."}
        self.events.add("self_healing.completed", result | {"run_id": context.get("run_id")}, session_id=context.get("session_id"))
        return result

    def attempts_for_run(self, run_id: str | None) -> int:
        if not run_id:
            return 0
        events = self.events.list_recent(limit=500)
        return sum(1 for event in events if event.type in {"self_healing.started", "self_healing.completed"} and event.payload.get("run_id") == run_id)

    def status(self) -> dict:
        return {
            "enabled": self.config.self_healing_enabled,
            "max_attempts": self.config.self_healing_max_attempts,
            "auto_apply_safe_recoveries": self.config.self_healing_auto_apply_safe_recoveries,
        }


def suggest_recovery(error: str) -> RecoverySuggestion | None:
    classified = classify_error(error)
    if classified.error_type == "unknown":
        return None
    return suggest_recovery_for_type(classified.error_type, {}, None)


def suggest_recovery_for_type(error_type: str, context: dict, config: OmegaConfig | None = None) -> RecoverySuggestion:
    if error_type == "command_not_found":
        return RecoverySuggestion("command_not_found", "Verifier que la commande est installee et presente dans PATH.")
    if error_type == "npm_missing":
        return RecoverySuggestion("npm_missing", "Installer Node.js/npm ou verifier que npm est disponible dans PATH.")
    if error_type == "python_missing":
        return RecoverySuggestion("python_missing", "Installer Python ou verifier que l'environnement virtuel du workspace est actif.")
    if error_type == "git_not_repository":
        return RecoverySuggestion("git_not_repository", "Changer de workspace ou initialiser un depot git local si c'est attendu.")
    if error_type == "permission_denied":
        return RecoverySuggestion("permission_denied", "Verifier que le chemin est dans le workspace et autorise par la policy Omega.")
    if error_type == "file_not_found":
        return RecoverySuggestion("file_not_found", "Verifier le chemin relatif et scanner le repo avant de relancer.")
    if error_type == "module_not_found":
        return RecoverySuggestion("module_not_found", "Verifier requirements.txt/pyproject.toml avant toute installation. Installer seulement dans le venv/workspace apres validation.")
    if error_type == "package_missing":
        allow = bool(config and config.code_allow_npm_install)
        message = "Verifier package.json avant npm install. npm install dans le workspace peut etre propose." if allow else "Verifier package.json; npm install est desactive par configuration."
        return RecoverySuggestion("package_missing", message)
    if error_type == "port_in_use":
        return RecoverySuggestion("port_in_use", "Identifier le PID qui occupe le port; ne pas tuer le processus sans approval explicite.")
    if error_type == "json_decode_error":
        return RecoverySuggestion("json_decode_error", "Relire le fichier en utf-8-sig ou corriger le JSON invalide/BOM.", safe_to_auto_apply=False)
    if error_type == "test_failure":
        return RecoverySuggestion("test_failure", "Analyser le premier test en echec, creer un patch minimal, puis relancer les tests.")
    if error_type == "syntax_error":
        return RecoverySuggestion("syntax_error", "Corriger la syntaxe dans le fichier signale puis relancer le test ou build cible.")
    if error_type == "type_error":
        return RecoverySuggestion("type_error", "Corriger le typage minimalement puis relancer le checker ou build.")
    if error_type == "network_error":
        return RecoverySuggestion("network_error", "Verifier que la commande ne depend pas du reseau ou relancer avec connectivite explicite.")
    if error_type == "config_error":
        return RecoverySuggestion("config_error", "Verifier config.json et les fichiers de configuration du projet.")
    return RecoverySuggestion("unknown", "Erreur non classifiee: demander une clarification ou inspecter les logs.")


def can_auto_recover(error_type: str, context: dict, config: OmegaConfig) -> bool:
    return SelfHealingEngine(config).can_auto_recover(error_type, context)


def attempt_recovery(error_type: str, context: dict, config: OmegaConfig) -> dict:
    return SelfHealingEngine(config).attempt_recovery(error_type, context)
