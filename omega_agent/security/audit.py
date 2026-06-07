from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.security.browser_policy import validate_browser_profile_dir
from omega_agent.security.desktop_policy import validate_desktop_screenshots_dir
from omega_agent.security.plugin_policy import PERMISSIONS
from omega_agent.security.prompt_injection import scan_untrusted_content
from omega_agent.security.redaction import redact
from omega_agent.storage import connect_db, migrate

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SENSITIVE_TOOL_IDS = {"write_file", "run_shell", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}
DANGEROUS_COMMANDS = {"sudo", "su", "rm", "rmdir", "del", "erase", "mkfs", "dd", "chmod", "chown", "shutdown", "reboot"}
SHELL_NETWORK_TERMS = {"run_shell", "shell", "curl", "wget", "invoke-webrequest", "http://", "https://", "network", "webhook"}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)token=[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)password=[^\s&]+"),
)


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    area: str
    finding: str
    recommendation: str
    auto_fix_available: bool = False


@dataclass(frozen=True)
class AuditReport:
    score: int
    generated_at: str
    findings: list[AuditFinding]
    fixed: list[str] | None = None

    def as_api(self) -> dict:
        return {
            "score": self.score,
            "generated_at": self.generated_at,
            "findings": [asdict(finding) for finding in self.findings],
            "fixed": self.fixed or [],
        }


def write_audit_log(config: OmegaConfig, action: str, payload: dict) -> None:
    migrate(config)
    with connect_db(config) as conn:
        conn.execute(
            "INSERT INTO audit_logs(id, action, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (uuid4().hex, action, json.dumps(redact(payload), ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )


def list_audit_logs(config: OmegaConfig, limit: int = 100) -> list[dict]:
    migrate(config)
    with connect_db(config) as conn:
        rows = conn.execute(
            "SELECT id, action, payload_json, created_at FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "action": row["action"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def run_security_audit(config: OmegaConfig) -> AuditReport:
    findings: list[AuditFinding] = []
    _audit_gateway(config, findings)
    _audit_workspace_full_access(config, findings)
    _audit_tools(config, findings)
    _audit_plugins(config, findings)
    _audit_skills(config, findings)
    _audit_channels(config, findings)
    _audit_scheduler(config, findings)
    _audit_browser_desktop(config, findings)
    _audit_secrets(config, findings)
    return AuditReport(score=_score(findings), generated_at=datetime.now(timezone.utc).isoformat(), findings=findings)


def apply_safe_fixes(config: OmegaConfig, env_path: Path | None = None) -> tuple[OmegaConfig, list[str]]:
    fixed: list[str] = []
    next_config = config
    env_updates: dict[str, str] = {}
    if not config.require_approval and not config.workspace_full_access:
        next_config = replace(next_config, require_approval=True)
        env_updates["OMEGA_REQUIRE_APPROVAL"] = "true"
        fixed.append("Approval global active.")
    if config.host == "0.0.0.0":
        next_config = replace(next_config, host="127.0.0.1")
        env_updates["OMEGA_HOST"] = "127.0.0.1"
        fixed.append("Host gateway remis sur 127.0.0.1.")
    fixed.extend(_disable_blocked_plugins(config))
    if env_updates:
        _update_env_file(env_path or Path(".env"), env_updates)
    write_audit_log(config, "security_audit_fix_safe", {"fixed": fixed})
    return next_config, fixed


def _audit_gateway(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    if config.host == "0.0.0.0":
        severity = "critical" if config.workspace_full_access else "high"
        findings.append(AuditFinding(severity, "gateway", "Gateway bind sur 0.0.0.0.", "Revenir a 127.0.0.1 sauf besoin LAN explicite.", True))
    elif config.host not in {"127.0.0.1", "localhost", "::1"}:
        findings.append(AuditFinding("medium", "gateway", f"Gateway bind non local: {config.host}.", "Utiliser 127.0.0.1 pour un agent local personnel."))
    else:
        findings.append(AuditFinding("info", "gateway", "Gateway bind local.", "Conserver le bind 127.0.0.1."))
    if not 1 <= int(config.port) <= 65535:
        findings.append(AuditFinding("critical", "gateway", "Port gateway invalide.", "Configurer un port TCP valide."))
    if _cors_middleware_present():
        findings.append(AuditFinding("medium", "gateway", "CORS middleware detecte.", "Verifier que CORS n'autorise pas '*' avec credentials."))
    else:
        findings.append(AuditFinding("info", "gateway", "Aucun CORS permissif detecte.", "Ne pas ajouter CORS global sauf besoin explicite."))
    findings.append(AuditFinding("info", "gateway", "Auth locale non disponible comme controle runtime dedie.", "Garder le bind local et eviter toute exposition LAN."))


def _audit_workspace_full_access(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    home = Path.home().resolve()
    workspace = config.workspace.resolve()
    if workspace == home or workspace.parent == workspace:
        findings.append(AuditFinding("critical", "workspace", "Workspace pointe vers HOME ou une racine disque.", "Configurer OMEGA_WORKSPACE vers un dossier projet dedie."))
        return
    if config.workspace_full_access:
        findings.append(AuditFinding("medium", "workspace", "Workspace Full Access actif : Omega peut modifier librement les fichiers dans le workspace.", "Conserver un workspace dedie et versionne."))
    else:
        findings.append(AuditFinding("info", "workspace", "Workspace Full Access inactif.", "Activer seulement pour un workspace dedie."))


def _audit_tools(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    from omega_agent.runtime.projects import ProjectsStore
    from omega_agent.runtime.tools_registry import ToolsRegistry

    tools = {tool.id: tool for tool in ToolsRegistry(config).list()}
    if "run_shell" in tools:
        severity = "medium" if config.workspace_full_access else "critical" if not config.require_approval else "medium"
        findings.append(AuditFinding(severity, "tools", "Tool run_shell disponible.", "Garder le shell borne au workspace et bloquer les commandes systeme.", not config.require_approval and not config.workspace_full_access))
    if "write_file" in tools:
        severity = "medium" if config.workspace_full_access else "critical" if not config.require_approval else "medium"
        findings.append(AuditFinding(severity, "tools", "Tool write_file disponible.", "Limiter le workspace et garder les secrets hors workspace.", not config.require_approval and not config.workspace_full_access))
    if not config.require_approval and not config.workspace_full_access and SENSITIVE_TOOL_IDS.intersection(tools):
        findings.append(AuditFinding("critical", "tools", "Tools sensibles sans approval globale.", "Activer OMEGA_REQUIRE_APPROVAL=true.", True))
    try:
        project = ProjectsStore(config).get("default", include_disabled=True)
        if project and not project.policy.shell_allowlist:
            findings.append(AuditFinding("medium", "tools", "Projet default sans shell_allowlist explicite.", "Declarer une allowlist shell minimale par projet."))
        if project and any(command in set(project.policy.shell_allowlist) for command in DANGEROUS_COMMANDS):
            findings.append(AuditFinding("critical", "tools", "Commande dangereuse detectee dans shell_allowlist.", "Retirer commandes destructrices de shell_allowlist."))
    except Exception as exc:
        findings.append(AuditFinding("low", "tools", f"Audit projet impossible: {exc}", "Verifier la base runtime."))


def _audit_plugins(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    from omega_agent.registries.plugins import PluginsRegistry

    for plugin in PluginsRegistry(config).list():
        raw_enabled = bool((plugin.raw_manifest or {}).get("enabled", plugin.enabled))
        if plugin.trust_level == "untrusted" and raw_enabled:
            severity = "critical" if config.workspace_full_access else "high"
            findings.append(AuditFinding(severity, "plugins", f"Plugin untrusted demande enabled: {plugin.id}.", "Laisser disabled; review manuelle requise."))
        if plugin.trust_level == "blocked":
            findings.append(AuditFinding("high", "plugins", f"Plugin blocked detecte: {plugin.id}.", "Le conserver disabled ou retirer le manifest apres review.", True))
        if plugin.status in {"rejected", "blocked"}:
            findings.append(AuditFinding("high", "plugins", f"Manifest plugin non chargeable: {plugin.id}.", plugin.error or "Corriger ou retirer le manifest.", True))
        critical_permissions = sorted(set(plugin.permissions or []) & {"shell.execute", "filesystem.write", "network.access", "browser.control", "desktop.control"})
        if critical_permissions:
            severity = "critical" if "shell.execute" in critical_permissions else "high"
            findings.append(AuditFinding(severity, "plugins", f"Plugin {plugin.id} demande permissions sensibles: {', '.join(critical_permissions)}.", "Refuser l'activation sans review de securite."))
        unknown = sorted(set(plugin.permissions or []) - PERMISSIONS)
        if unknown:
            findings.append(AuditFinding("critical", "plugins", f"Plugin {plugin.id} declare permissions inconnues.", "Corriger le manifest."))


def _audit_skills(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    from omega_agent.runtime.skills_registry import SkillsRegistry

    root = (config.skills_dir or Path("~/omega_skills").expanduser()).resolve()
    for skill in SkillsRegistry(config).list():
        path = Path(skill.path).resolve()
        try:
            if os.path.commonpath([str(root), str(path)]) != str(root):
                findings.append(AuditFinding("high", "skills", f"Skill hors skills_dir: {skill.id}.", "Deplacer la skill sous OMEGA_SKILLS_DIR."))
        except ValueError:
            findings.append(AuditFinding("high", "skills", f"Skill sur volume hors skills_dir: {skill.id}.", "Deplacer la skill sous OMEGA_SKILLS_DIR."))
        scan = scan_untrusted_content(skill.instructions)
        if scan.matches:
            findings.append(AuditFinding("high", "skills", f"Instructions suspectes dans skill {skill.id}.", "Relire la skill et retirer les instructions de bypass."))
        broad_tools = set(skill.allowed_tools or []) & {"run_shell", "write_file", "browser_click", "browser_type", "desktop_click", "desktop_type", "desktop_hotkey"}
        if broad_tools:
            findings.append(AuditFinding("medium", "skills", f"Skill {skill.id} autorise tools sensibles: {', '.join(sorted(broad_tools))}.", "Limiter allowed_tools au strict necessaire."))


def _audit_channels(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    from omega_agent.channels.registry import ChannelsRegistry

    try:
        channels = ChannelsRegistry(config).list()
    except Exception as exc:
        findings.append(AuditFinding("low", "channels", f"Audit channels impossible: {exc}", "Verifier la base runtime."))
        return
    for channel in channels:
        if channel.type in {"telegram", "discord", "webhook"} and channel.enabled:
            severity = "high" if not config.require_approval else "medium"
            findings.append(AuditFinding(severity, "channels", f"Channel externe enabled: {channel.id}.", "Verifier untrusted_input et approvals high/critical."))
    if (config.telegram_enabled or config.discord_enabled or config.webhooks_enabled) and not config.require_approval:
        findings.append(AuditFinding("high", "channels", "Channels externes possibles sans approval globale.", "Activer OMEGA_REQUIRE_APPROVAL=true.", True))


def _audit_scheduler(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    from omega_agent.runtime.scheduler import ScheduledTasksStore

    if config.scheduler_enabled:
        findings.append(AuditFinding("medium", "scheduler", "Scheduler active.", "Garder approvals sensibles et auditer les prompts planifies."))
    try:
        for task in ScheduledTasksStore(config).list():
            haystack = f"{task.prompt} {task.metadata_json}".lower()
            if task.enabled and any(term in haystack for term in SHELL_NETWORK_TERMS):
                severity = "critical" if not config.require_approval else "high"
                findings.append(AuditFinding(severity, "scheduler", f"Tache planifiee sensible: {task.title}.", "Exiger approval et limiter shell/network."))
    except Exception:
        return


def _audit_browser_desktop(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    if config.browser_enabled:
        findings.append(AuditFinding("medium", "browser", "Browser automation active.", "Verifier profil isole et approval obligatoire."))
        if not config.browser_require_approval:
            severity = "critical" if config.workspace_full_access else "high"
            findings.append(AuditFinding(severity, "browser", "Browser actions sans approval dediee.", "Activer OMEGA_BROWSER_REQUIRE_APPROVAL=true."))
    try:
        validate_browser_profile_dir(config)
    except PermissionError as exc:
        findings.append(AuditFinding("critical", "browser", f"Profil browser invalide: {exc}", "Utiliser un profil isole sous OMEGA_WORKSPACE/.omega/browser-profile."))
    if config.desktop_enabled:
        findings.append(AuditFinding("medium", "desktop", "Desktop automation active.", "Garder l'usage visible et approuve."))
        if not config.desktop_require_approval:
            findings.append(AuditFinding("critical", "desktop", "Desktop click/type/hotkey sans approval dediee.", "Activer OMEGA_DESKTOP_REQUIRE_APPROVAL=true."))
    try:
        validate_desktop_screenshots_dir(config)
    except PermissionError as exc:
        findings.append(AuditFinding("high", "desktop", f"Dossier screenshots desktop invalide: {exc}", "Utiliser OMEGA_WORKSPACE/.omega/screenshots."))


def _audit_secrets(config: OmegaConfig, findings: list[AuditFinding]) -> None:
    log_file = config.workspace / ".omega" / "actions.jsonl"
    if log_file.exists():
        sample = log_file.read_text(encoding="utf-8", errors="replace")[-200000:]
        if any(pattern.search(sample) for pattern in SECRET_PATTERNS):
            findings.append(AuditFinding("critical", "secrets", "Secret potentiel expose dans actions.jsonl.", "Verifier redaction et rotationner les tokens exposes."))
    findings.append(AuditFinding("info", "secrets", "Redaction active via security.redaction.", "Continuer a ne pas exposer tokens dans API/UI."))


def _score(findings: list[AuditFinding]) -> int:
    penalty = {"info": 0, "low": 2, "medium": 6, "high": 14, "critical": 30}
    return max(0, 100 - sum(penalty.get(finding.severity, 0) for finding in findings))


def _disable_blocked_plugins(config: OmegaConfig) -> list[str]:
    from omega_agent.registries.plugins import PluginsRegistry

    fixed: list[str] = []
    for plugin in PluginsRegistry(config).list():
        if plugin.trust_level != "blocked":
            continue
        path = Path(plugin.path)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("enabled") is True:
            data["enabled"] = False
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed.append(f"Plugin blocked desactive: {plugin.id}.")
    return fixed


def _update_env_file(path: Path, values: dict[str, str]) -> None:
    if not path.exists():
        path.write_text("", encoding="utf-8")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in values:
            next_lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in values.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")
    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def _cors_middleware_present() -> bool:
    for path in Path("omega_agent").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "CORSMiddleware" in text or "allow_origins=[\"*\"]" in text:
            return True
    return False
