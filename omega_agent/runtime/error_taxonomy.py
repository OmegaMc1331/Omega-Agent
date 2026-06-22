from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from omega_agent.security.redaction import redact

ERROR_TYPES = {
    "file_not_found",
    "command_not_found",
    "module_not_found",
    "package_missing",
    "test_failure",
    "syntax_error",
    "type_error",
    "git_not_repository",
    "npm_missing",
    "python_missing",
    "permission_denied",
    "port_in_use",
    "json_decode_error",
    "config_error",
    "network_error",
    "unknown",
}


@dataclass(frozen=True)
class ClassifiedError:
    error_type: str
    title: str
    summary: str
    confidence: float = 0.7
    metadata: dict | None = None

    def as_api(self) -> dict:
        return redact(asdict(self))


def classify_error(error_text: str, context: dict | None = None) -> ClassifiedError:
    text = str(error_text or "")
    lowered = text.lower()
    metadata = dict(context or {})
    if "not a git repository" in lowered:
        return _classified("git_not_repository", "Git repository missing", "La commande git a ete lancee hors depot git.", 0.95, metadata)
    if "eaddrinuse" in lowered or "address already in use" in lowered or "port" in lowered and "in use" in lowered:
        return _classified("port_in_use", "Port already in use", "Un port requis est deja occupe.", 0.9, metadata)
    if "jsondecodeerror" in lowered or "json decode" in lowered or "unexpected utf-8 bom" in lowered or "unexpected token" in lowered and "json" in lowered:
        return _classified("json_decode_error", "JSON parse error", "Un fichier ou payload JSON est invalide ou encode avec BOM.", 0.85, metadata)
    if "modulenotfounderror" in lowered or re.search(r"no module named ['\"]?[\w.\-]+", lowered):
        return _classified("module_not_found", "Python module missing", "Un module Python requis est absent.", 0.9, metadata)
    if "cannot find module" in lowered or "module not found" in lowered:
        return _classified("package_missing", "Node package missing", "Un package Node requis est absent.", 0.85, metadata)
    if "npm" in lowered and ("not recognized" in lowered or "not found" in lowered or "introuvable" in lowered):
        return _classified("npm_missing", "npm missing", "npm n'est pas disponible dans le PATH.", 0.95, metadata)
    if ("python" in lowered or "py " in lowered) and ("not recognized" in lowered or "not found" in lowered or "introuvable" in lowered):
        return _classified("python_missing", "Python missing", "Python n'est pas disponible dans le PATH.", 0.9, metadata)
    if "command not found" in lowered or "not recognized" in lowered or "commande introuvable" in lowered or "introuvable sur cette machine" in lowered:
        return _classified("command_not_found", "Command missing", "La commande demandee n'est pas disponible.", 0.85, metadata)
    if "permission denied" in lowered or "access is denied" in lowered or "acces refuse" in lowered or "accès refus" in lowered:
        return _classified("permission_denied", "Permission denied", "L'action a ete refusee par le systeme de fichiers ou la policy.", 0.9, metadata)
    if "filenotfounderror" in lowered or "file not found" in lowered or "no such file or directory" in lowered or "fichier introuvable" in lowered:
        return _classified("file_not_found", "File missing", "Un fichier attendu est introuvable.", 0.85, metadata)
    if "syntaxerror" in lowered or "syntax error" in lowered:
        return _classified("syntax_error", "Syntax error", "Le code contient une erreur de syntaxe.", 0.9, metadata)
    if "typeerror" in lowered or "type error" in lowered or "tsc" in lowered and "error ts" in lowered:
        return _classified("type_error", "Type error", "Le code contient une erreur de typage.", 0.8, metadata)
    if "failed" in lowered and ("pytest" in lowered or "test" in lowered or "assert" in lowered):
        return _classified("test_failure", "Test failure", "Un ou plusieurs tests echouent.", 0.8, metadata)
    if "network" in lowered or "getaddrinfo" in lowered or "econnrefused" in lowered or "timeout" in lowered:
        return _classified("network_error", "Network error", "Erreur reseau ou timeout.", 0.7, metadata)
    if "config" in lowered or "configuration" in lowered:
        return _classified("config_error", "Configuration error", "Erreur de configuration detectee.", 0.65, metadata)
    return _classified("unknown", "Unknown error", text.strip()[:500] or "Erreur non classifiee.", 0.3, metadata)


def _classified(error_type: str, title: str, summary: str, confidence: float, metadata: dict) -> ClassifiedError:
    return ClassifiedError(error_type if error_type in ERROR_TYPES else "unknown", title, summary, confidence, metadata)
