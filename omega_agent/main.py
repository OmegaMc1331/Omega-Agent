from __future__ import annotations

import asyncio
import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from .config import OmegaConfig
from .doctor import run_doctor
from .runtime import OmegaRuntime
from .runtime.jobs import JobsStore
from .runtime.memory import MemoryStore
from .runtime.model_selector import ModelSelector
from .runtime.plugins_registry import PluginsRegistry
from .runtime.settings import SettingsStore
from .runtime.skills_registry import SkillsRegistry
from .runtime.tools_registry import list_tools
from .security.audit import apply_safe_fixes, run_security_audit
from .tools.memory import _recall

console = Console()


async def chat_loop() -> None:
    load_dotenv()
    config = OmegaConfig.from_env()
    try:
        runtime = OmegaRuntime(config)
    except RuntimeError as exc:
        console.print(f"[bold red]Erreur:[/bold red] {exc}")
        return

    console.print("[bold]Ω Omega Agent[/bold]")
    console.print(f"Provider: {config.provider}")
    console.print(f"Modèle: {config.model}")
    console.print(f"Workspace: {config.workspace}")
    console.print("Tape /help pour afficher les commandes.\n")

    while True:
        try:
            user_input = input("Ω > ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nAu revoir.")
            return

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            return
        if user_input == "/workspace":
            console.print(str(config.workspace))
            continue
        if user_input == "/model":
            console.print(config.model)
            continue
        if user_input == "/provider":
            console.print(config.provider)
            continue
        if user_input == "/memory":
            console.print(_recall(config, ""))
            continue
        if user_input == "/help":
            console.print("Commandes: /help, /workspace, /provider, /model, /memory, /exit")
            continue

        output = await runtime.send_message(user_input)
        console.print(f"\n[bold cyan]Omega:[/bold cyan] {output}\n")


def doctor_command() -> int:
    load_dotenv()
    try:
        config = OmegaConfig.from_env()
    except Exception as exc:
        console.print(f"[red]FAIL Config:[/red] {exc}")
        return 1

    checks = run_doctor(config)
    for check in checks:
        marker = "[green]OK[/green]" if check.ok else "[red]FAIL[/red]"
        console.print(f"{marker} {check.name}: {check.detail}")
    if config.provider == "codex" and not next(check.ok for check in checks if check.name == "Auth Codex"):
        console.print("Lance d'abord : codex login")
    return 0 if all(check.ok for check in checks) else 1


def run() -> None:
    parser = argparse.ArgumentParser(prog="omega")
    subparsers = parser.add_subparsers(dest="command")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--no-open", action="store_true")
    subparsers.add_parser("chat")
    subparsers.add_parser("doctor")
    ui_parser = subparsers.add_parser("ui")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_command")
    ui_subparsers.add_parser("dev")
    skills_parser = subparsers.add_parser("skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")
    skills_subparsers.add_parser("list")
    skills_create = skills_subparsers.add_parser("create")
    skills_create.add_argument("name")
    skills_create.add_argument("--description", default="")
    skills_create.add_argument("--risk", default="low")
    plugins_parser = subparsers.add_parser("plugins")
    plugins_subparsers = plugins_parser.add_subparsers(dest="plugins_command")
    plugins_subparsers.add_parser("list")
    tools_parser = subparsers.add_parser("tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command")
    tools_subparsers.add_parser("list")
    models_parser = subparsers.add_parser("models")
    models_subparsers = models_parser.add_subparsers(dest="models_command")
    models_subparsers.add_parser("list")
    models_subparsers.add_parser("providers")
    models_subparsers.add_parser("status")
    models_subparsers.add_parser("current")
    models_subparsers.add_parser("refresh")
    models_subparsers.add_parser("auth-status")
    models_set = models_subparsers.add_parser("set")
    models_set.add_argument("model_ref")
    models_test = models_subparsers.add_parser("test")
    models_test.add_argument("model_ref")
    jobs_parser = subparsers.add_parser("jobs")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command")
    jobs_subparsers.add_parser("list")
    memory_parser = subparsers.add_parser("memory")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    memory_search = memory_subparsers.add_parser("search")
    memory_search.add_argument("query", nargs="?", default="")
    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("show")
    security_parser = subparsers.add_parser("security")
    security_subparsers = security_parser.add_subparsers(dest="security_command")
    security_audit = security_subparsers.add_parser("audit")
    security_audit.add_argument("--json", action="store_true", dest="json_output")
    security_audit.add_argument("--fix-safe", action="store_true")
    args = parser.parse_args()

    if args.command == "doctor":
        raise SystemExit(doctor_command())
    if args.command == "chat":
        asyncio.run(chat_loop())
        return
    if args.command == "ui" and args.ui_command == "dev":
        raise SystemExit(ui_dev_command())
    if args.command == "skills":
        raise SystemExit(skills_command(args))
    if args.command == "plugins":
        raise SystemExit(plugins_command(args))
    if args.command == "tools":
        raise SystemExit(tools_command(args))
    if args.command == "models":
        raise SystemExit(models_command(args))
    if args.command == "jobs":
        raise SystemExit(jobs_command(args))
    if args.command == "memory":
        raise SystemExit(memory_command(args))
    if args.command == "config":
        raise SystemExit(config_command(args))
    if args.command == "security":
        raise SystemExit(security_command(args))
    if args.command in {None, "serve"}:
        load_dotenv()
        config = OmegaConfig.from_env()
        host = getattr(args, "host", None) or config.host
        port = getattr(args, "port", None) or config.port
        open_browser = args.command is None and config.open_browser and not getattr(args, "no_open", False)
        if host not in {"127.0.0.1", "localhost", "::1"}:
            console.print("[bold yellow]Avertissement sécurité:[/bold yellow] Omega Gateway sera accessible hors boucle locale. N'utilisez cela que sur un réseau de confiance.")
        from .gateway.server import serve_gateway

        try:
            serve_gateway(config, host=host, port=port, open_browser=open_browser, reuse_existing=args.command is None)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc
        return
    console.print("Commande inconnue. Commandes: serve, chat, doctor, ui, skills, plugins, tools, security")
    raise SystemExit(2)


def ui_dev_command() -> int:
    ui_dir = Path(__file__).resolve().parents[1] / "omega_control"
    if not ui_dir.exists():
        console.print("[red]Omega Control introuvable.[/red]")
        return 1
    try:
        subprocess.run(["npm", "run", "dev"], cwd=ui_dir, check=False)
    except FileNotFoundError:
        console.print("[red]npm introuvable. Installe Node.js puis lance npm install dans omega_control.[/red]")
        return 1
    return 0


def skills_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    registry = SkillsRegistry(config)
    if args.skills_command == "list":
        for skill in registry.list():
            console.print(f"{skill.name} ({skill.risk}) {'enabled' if skill.enabled else 'disabled'} - {skill.description}")
        return 0
    if args.skills_command == "create":
        skill = registry.create(args.name, args.description, risk=args.risk)
        console.print(f"Skill créée: {skill.path}")
        return 0
    console.print("Commandes: omega skills list, omega skills create <name>")
    return 2


def plugins_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    if args.plugins_command == "list":
        for plugin in PluginsRegistry(config).list():
            console.print(f"{plugin.name} ({plugin.status}) - {plugin.path}")
        return 0
    console.print("Commandes: omega plugins list")
    return 2


def tools_command(args: argparse.Namespace) -> int:
    if args.tools_command == "list":
        for tool in list_tools():
            marker = "approval" if tool.requires_approval else "direct"
            console.print(f"{tool.id} ({tool.risk}/{marker}) {tool.description}")
        return 0
    console.print("Commandes: omega tools list")
    return 2


def models_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    selector = ModelSelector(config)
    if args.models_command == "list":
        for model in selector.catalog_api():
            marker = "available" if model["available"] else "unavailable"
            console.print(f"{model['model_ref']} ({marker}, {model['speed_tier']}/{model['cost_tier']}) - {model['display_name']}")
        return 0
    if args.models_command == "providers":
        for provider in selector.providers_api():
            console.print(f"{provider['id']} ({provider['auth_type']}) {provider['status']} - {provider['name']}")
        return 0
    if args.models_command in {"status", "auth-status"}:
        for status in selector.status_api(force=True):
            console.print(f"{status['provider_id']}: {status['status']} ({status['auth_method']})")
        return 0
    if args.models_command == "current":
        current = selector.current_api()
        console.print(f"{current['primary_model_ref']} (source={current['source_scope']})")
        if current.get("fallback_model_ref"):
            console.print(f"fallback: {current['fallback_model_ref']}")
        return 0
    if args.models_command == "set":
        preference = selector.set_preference("global", args.model_ref)
        console.print(f"Modèle global: {preference.primary_model_ref}")
        return 0
    if args.models_command == "test":
        provider_id = args.model_ref.split("/", 1)[0]
        provider = selector.provider(provider_id)
        if provider is None:
            console.print("[red]Provider inconnu.[/red]")
            return 1
        status = provider.check_auth()
        console.print(f"{provider_id}: {status.status}")
        return 0 if status.status in {"configured", "unknown"} or provider.auth_type == "none" else 1
    if args.models_command == "refresh":
        result = selector.refresh_catalog()
        console.print(f"Catalogue rafraîchi: {result['count']} modèles")
        return 0
    console.print("Commandes: omega models list|providers|status|current|set <provider/model>|test <provider/model>|refresh|auth-status")
    return 2


def jobs_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    if args.jobs_command == "list":
        for job in JobsStore(config).list():
            console.print(f"{job.id} {job.status} {job.kind} - {job.title}")
        return 0
    console.print("Commandes: omega jobs list")
    return 2


def memory_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    if args.memory_command == "search":
        for memory in MemoryStore(config).search(args.query):
            console.print(f"{memory.id} [{memory.scope}] {memory.key}: {memory.content}")
        return 0
    console.print("Commandes: omega memory search [query]")
    return 2


def config_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    if args.config_command == "show":
        settings = SettingsStore(config).get_all()
        for key, value in settings.items():
            console.print(f"{key}: {value}")
        return 0
    console.print("Commandes: omega config show")
    return 2


def security_command(args: argparse.Namespace) -> int:
    load_dotenv()
    config = OmegaConfig.from_env()
    fixed: list[str] = []
    if args.security_command == "audit":
        if args.fix_safe:
            config, fixed = apply_safe_fixes(config, env_path=Path(".env"))
        report = run_security_audit(config)
        if fixed:
            report = type(report)(score=report.score, generated_at=report.generated_at, findings=report.findings, fixed=fixed)
        if args.json_output:
            sys.stdout.write(json.dumps(report.as_api(), ensure_ascii=False, indent=2) + "\n")
        else:
            console.print(f"[bold]Omega Security Audit[/bold] score={report.score}/100")
            for item in report.findings:
                color = {"critical": "red", "high": "red", "medium": "yellow", "low": "cyan", "info": "green"}.get(item.severity, "white")
                console.print(f"[{color}]{item.severity.upper()}[/{color}] {item.area}: {item.finding}")
                console.print(f"  -> {item.recommendation}")
            if fixed:
                console.print("[bold green]Safe fixes applied:[/bold green]")
                for item in fixed:
                    console.print(f"  - {item}")
        return 2 if any(f.severity == "critical" for f in report.findings) else 1 if any(f.severity in {"high", "medium"} for f in report.findings) else 0
    console.print("Commandes: omega security audit [--json] [--fix-safe]")
    return 2


if __name__ == "__main__":
    run()
