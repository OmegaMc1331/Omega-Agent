from __future__ import annotations

import asyncio
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from dotenv import load_dotenv
from rich.console import Console

from .runtime.context import runtime_context

console = Console()


def _load_legacy_dotenv_if_needed() -> None:
    from .config_store import config_path

    if config_path().exists():
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    load_dotenv()


async def chat_loop() -> None:
    from .config import OmegaConfig
    from .runtime import OmegaRuntime
    from .tools.memory import _recall

    _load_legacy_dotenv_if_needed()
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
    from .config import OmegaConfig
    from .doctor import run_doctor

    _load_legacy_dotenv_if_needed()
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


def main(argv: Sequence[str] | None = None) -> int:
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
    skills_show = skills_subparsers.add_parser("show")
    skills_show.add_argument("skill_id")
    skills_subparsers.add_parser("candidates")
    skills_subparsers.add_parser("detect")
    skills_accept = skills_subparsers.add_parser("accept")
    skills_accept.add_argument("candidate_id")
    skills_reject = skills_subparsers.add_parser("reject")
    skills_reject.add_argument("candidate_id")
    skills_test = skills_subparsers.add_parser("test")
    skills_test.add_argument("skill_id")
    skills_activate = skills_subparsers.add_parser("activate")
    skills_activate.add_argument("skill_id")
    skills_disable = skills_subparsers.add_parser("disable")
    skills_disable.add_argument("skill_id")
    skills_create = skills_subparsers.add_parser("create")
    skills_create.add_argument("name")
    skills_create.add_argument("--description", default="")
    skills_create.add_argument("--risk", default="low")
    budgets_parser = subparsers.add_parser("budgets")
    budgets_subparsers = budgets_parser.add_subparsers(dest="budgets_command")
    budgets_subparsers.add_parser("profiles")
    budgets_show = budgets_subparsers.add_parser("show")
    budgets_show.add_argument("profile_id")
    budgets_subparsers.add_parser("usage")
    budgets_subparsers.add_parser("violations")
    budgets_simulate = budgets_subparsers.add_parser("simulate")
    budgets_simulate.add_argument("--tool", default="read_file")
    budgets_simulate.add_argument("--risk", default="low")
    budgets_simulate.add_argument("--category", default="read_only")
    budgets_simulate.add_argument("--run", default=None)
    budgets_subparsers.add_parser("doctor")
    shadow_parser = subparsers.add_parser("shadow")
    shadow_subparsers = shadow_parser.add_subparsers(dest="shadow_command")
    shadow_create = shadow_subparsers.add_parser("create")
    shadow_create.add_argument("objective")
    shadow_run = shadow_subparsers.add_parser("run")
    shadow_run.add_argument("shadow_run_id")
    shadow_show = shadow_subparsers.add_parser("show")
    shadow_show.add_argument("shadow_run_id")
    shadow_diff = shadow_subparsers.add_parser("diff")
    shadow_diff.add_argument("shadow_run_id")
    shadow_risk = shadow_subparsers.add_parser("risk")
    shadow_risk.add_argument("shadow_run_id")
    shadow_promote = shadow_subparsers.add_parser("promote")
    shadow_promote.add_argument("shadow_run_id")
    shadow_promote.add_argument("--approved-by", default=None)
    shadow_reject = shadow_subparsers.add_parser("reject")
    shadow_reject.add_argument("shadow_run_id")
    shadow_subparsers.add_parser("list")
    plugins_parser = subparsers.add_parser("plugins")
    plugins_subparsers = plugins_parser.add_subparsers(dest="plugins_command")
    plugins_subparsers.add_parser("list")
    tools_parser = subparsers.add_parser("tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command")
    tools_subparsers.add_parser("list")
    tools_test = tools_subparsers.add_parser("test")
    tools_test.add_argument("test_name", choices=["write-file", "shell"])
    workspace_parser = subparsers.add_parser("workspace")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command")
    workspace_subparsers.add_parser("doctor")
    mobile_parser = subparsers.add_parser("mobile")
    mobile_subparsers = mobile_parser.add_subparsers(dest="mobile_command")
    tailscale_parser = mobile_subparsers.add_parser("tailscale")
    tailscale_subparsers = tailscale_parser.add_subparsers(dest="tailscale_command")
    for name in ("status", "serve", "stop", "url"):
        tailscale_subparsers.add_parser(name)
    models_parser = subparsers.add_parser("models")
    models_subparsers = models_parser.add_subparsers(dest="models_command")
    models_subparsers.add_parser("list")
    models_subparsers.add_parser("providers")
    models_subparsers.add_parser("status")
    models_subparsers.add_parser("current")
    models_subparsers.add_parser("refresh")
    models_subparsers.add_parser("auth-status")
    models_set_default = models_subparsers.add_parser("set-default")
    models_set_default.add_argument("model_ref")
    models_set_fallback = models_subparsers.add_parser("set-fallback")
    models_set_fallback.add_argument("model_ref")
    models_enable_provider = models_subparsers.add_parser("enable-provider")
    models_enable_provider.add_argument("provider")
    models_disable_provider = models_subparsers.add_parser("disable-provider")
    models_disable_provider.add_argument("provider")
    models_base_url = models_subparsers.add_parser("set-provider-base-url")
    models_base_url.add_argument("provider")
    models_base_url.add_argument("url")
    models_set = models_subparsers.add_parser("set")
    models_set.add_argument("model_ref")
    models_test = models_subparsers.add_parser("test")
    models_test.add_argument("model_ref")
    jobs_parser = subparsers.add_parser("jobs")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command")
    jobs_subparsers.add_parser("list")
    runs_parser = subparsers.add_parser("runs")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command")
    runs_subparsers.add_parser("list")
    runs_show = runs_subparsers.add_parser("show")
    runs_show.add_argument("run_id")
    runs_resume = runs_subparsers.add_parser("resume")
    runs_resume.add_argument("run_id")
    runs_cancel = runs_subparsers.add_parser("cancel")
    runs_cancel.add_argument("run_id")
    runs_replay = runs_subparsers.add_parser("replay")
    runs_replay.add_argument("run_id")
    runs_score = runs_subparsers.add_parser("score")
    runs_score.add_argument("run_id")
    runs_outcome = runs_subparsers.add_parser("outcome")
    runs_outcome.add_argument("run_id")
    runs_outcome.add_argument("outcome", choices=["success", "partial", "failed", "blocked", "cancelled", "unknown"])
    rollback_parser = subparsers.add_parser("rollback")
    rollback_subparsers = rollback_parser.add_subparsers(dest="rollback_command")
    rollback_subparsers.add_parser("list")
    rollback_run = rollback_subparsers.add_parser("run")
    rollback_run.add_argument("run_id")
    rollback_snapshot = rollback_subparsers.add_parser("snapshot")
    rollback_snapshot.add_argument("snapshot_id")
    runtime_parser = subparsers.add_parser("runtime")
    runtime_subparsers = runtime_parser.add_subparsers(dest="runtime_command")
    runtime_subparsers.add_parser("doctor")
    workflows_parser = subparsers.add_parser("workflows")
    workflows_subparsers = workflows_parser.add_subparsers(dest="workflows_command")
    workflows_subparsers.add_parser("list")
    workflows_subparsers.add_parser("templates")
    workflows_create = workflows_subparsers.add_parser("create")
    workflows_create.add_argument("--file", default="")
    workflows_create.add_argument("--template", default="")
    workflows_create.add_argument("--name", default="")
    workflows_show = workflows_subparsers.add_parser("show")
    workflows_show.add_argument("workflow", nargs="+")
    workflows_run = workflows_subparsers.add_parser("run")
    workflows_run.add_argument("workflow", nargs="+")
    workflows_runs = workflows_subparsers.add_parser("runs")
    workflows_runs.add_argument("--status", default=None)
    workflows_status = workflows_subparsers.add_parser("status")
    workflows_status.add_argument("workflow_run_id")
    workflows_pause = workflows_subparsers.add_parser("pause")
    workflows_pause.add_argument("workflow_run_id")
    workflows_resume = workflows_subparsers.add_parser("resume")
    workflows_resume.add_argument("workflow_run_id")
    workflows_cancel = workflows_subparsers.add_parser("cancel")
    workflows_cancel.add_argument("workflow_run_id")
    workflows_retry = workflows_subparsers.add_parser("retry-step")
    workflows_retry.add_argument("workflow_run_id")
    workflows_retry.add_argument("step_id")
    evals_parser = subparsers.add_parser("evals")
    evals_subparsers = evals_parser.add_subparsers(dest="evals_command")
    evals_subparsers.add_parser("list")
    evals_run = evals_subparsers.add_parser("run")
    evals_run.add_argument("dataset")
    evals_subparsers.add_parser("report")
    evals_subparsers.add_parser("failures")
    evals_subparsers.add_parser("metrics")
    traces_parser = subparsers.add_parser("traces")
    traces_subparsers = traces_parser.add_subparsers(dest="traces_command")
    traces_subparsers.add_parser("list")
    traces_show = traces_subparsers.add_parser("show")
    traces_show.add_argument("run_id")
    traces_export = traces_subparsers.add_parser("export")
    traces_export.add_argument("run_id")
    traces_subparsers.add_parser("analyze")
    events_parser = subparsers.add_parser("events")
    events_subparsers = events_parser.add_subparsers(dest="events_command")
    events_list = events_subparsers.add_parser("list")
    events_list.add_argument("--limit", type=int, default=20)
    events_list.add_argument("--type", default=None)
    events_list.add_argument("--run", dest="run_id", default=None)
    events_show = events_subparsers.add_parser("show")
    events_show.add_argument("event_id")
    events_replay = events_subparsers.add_parser("replay")
    events_replay.add_argument("--run", dest="run_id", default=None)
    events_replay.add_argument("--session", dest="session_id", default=None)
    events_replay.add_argument("--since-id", default=None)
    events_replay.add_argument("--limit", type=int, default=None)
    events_tail = events_subparsers.add_parser("tail")
    events_tail.add_argument("--limit", type=int, default=20)
    events_subparsers.add_parser("types")
    research_parser = subparsers.add_parser("research")
    research_subparsers = research_parser.add_subparsers(dest="research_command")
    research_start = research_subparsers.add_parser("start")
    research_start.add_argument("question")
    research_start.add_argument("--title", default=None)
    research_subparsers.add_parser("list")
    research_show = research_subparsers.add_parser("show")
    research_show.add_argument("research_run_id")
    research_export = research_subparsers.add_parser("export")
    research_export.add_argument("research_run_id")
    research_export.add_argument("--format", choices=["markdown", "json"], default="markdown")
    research_sources = research_subparsers.add_parser("sources")
    research_sources.add_argument("research_run_id")
    research_claims = research_subparsers.add_parser("claims")
    research_claims.add_argument("research_run_id")
    policy_parser = subparsers.add_parser("policy")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command")
    policy_subparsers.add_parser("profiles")
    policy_subparsers.add_parser("rules")
    policy_show = policy_subparsers.add_parser("show")
    policy_show.add_argument("profile_id")
    policy_enable = policy_subparsers.add_parser("enable")
    policy_enable.add_argument("profile_id")
    policy_disable = policy_subparsers.add_parser("disable")
    policy_disable.add_argument("profile_id")
    policy_add_rule = policy_subparsers.add_parser("add-rule")
    policy_add_rule.add_argument("--profile", default="developer-workspace")
    policy_add_rule.add_argument("--name", required=True)
    policy_add_rule.add_argument("--effect", choices=["allow", "deny", "require_approval"], required=True)
    policy_add_rule.add_argument("--tool", default=None)
    policy_add_rule.add_argument("--action-type", default=None)
    policy_add_rule.add_argument("--resource", default=None)
    policy_add_rule.add_argument("--risk-min", default=None)
    policy_add_rule.add_argument("--condition", action="append", default=[])
    policy_add_rule.add_argument("--priority", type=int, default=0)
    policy_add_rule.add_argument("--reason", default="")
    policy_simulate = policy_subparsers.add_parser("simulate")
    policy_simulate.add_argument("--tool", required=True)
    policy_simulate.add_argument("--path", default=None)
    policy_simulate.add_argument("--command", dest="shell_command", default=None)
    policy_simulate.add_argument("--file-count", type=int, default=0)
    policy_simulate.add_argument("--channel", default="local")
    policy_simulate.add_argument("--source-trust", default="local")
    policy_simulate.add_argument("--agent-profile", default=None)
    policy_subparsers.add_parser("doctor")
    capabilities_parser = subparsers.add_parser("capabilities")
    capabilities_subparsers = capabilities_parser.add_subparsers(dest="capabilities_command")
    capabilities_subparsers.add_parser("list")
    capabilities_show = capabilities_subparsers.add_parser("show")
    capabilities_show.add_argument("capability_id")
    capabilities_enable = capabilities_subparsers.add_parser("enable")
    capabilities_enable.add_argument("capability_id")
    capabilities_disable = capabilities_subparsers.add_parser("disable")
    capabilities_disable.add_argument("capability_id")
    capabilities_subparsers.add_parser("refresh")
    capabilities_search = capabilities_subparsers.add_parser("search")
    capabilities_search.add_argument("query")
    mcp_parser = subparsers.add_parser("mcp")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("list")
    mcp_add = mcp_subparsers.add_parser("add")
    mcp_add.add_argument("--name", required=True)
    mcp_add.add_argument("--url", default=None)
    mcp_add.add_argument("--command", default=None)
    mcp_enable = mcp_subparsers.add_parser("enable")
    mcp_enable.add_argument("server_id")
    mcp_disable = mcp_subparsers.add_parser("disable")
    mcp_disable.add_argument("server_id")
    mcp_subparsers.add_parser("status")
    a2a_parser = subparsers.add_parser("a2a")
    a2a_subparsers = a2a_parser.add_subparsers(dest="a2a_command")
    a2a_subparsers.add_parser("list")
    a2a_add = a2a_subparsers.add_parser("add")
    a2a_add.add_argument("--name", required=True)
    a2a_add.add_argument("--endpoint", default=None)
    a2a_enable = a2a_subparsers.add_parser("enable")
    a2a_enable.add_argument("agent_id")
    a2a_disable = a2a_subparsers.add_parser("disable")
    a2a_disable.add_argument("agent_id")
    a2a_subparsers.add_parser("status")
    connectors_parser = subparsers.add_parser("connectors")
    connectors_subparsers = connectors_parser.add_subparsers(dest="connectors_command")
    connectors_subparsers.add_parser("list")
    connectors_show = connectors_subparsers.add_parser("show")
    connectors_show.add_argument("connector_id")
    connectors_enable = connectors_subparsers.add_parser("enable")
    connectors_enable.add_argument("connector_id")
    connectors_disable = connectors_subparsers.add_parser("disable")
    connectors_disable.add_argument("connector_id")
    connectors_test = connectors_subparsers.add_parser("test")
    connectors_test.add_argument("connector_id")
    connectors_import = connectors_subparsers.add_parser("import-openapi")
    connectors_import.add_argument("path")
    connectors_import.add_argument("--name", default=None)
    connectors_import.add_argument("--base-url", default=None)
    connectors_import.add_argument("--trust-level", default="local")
    connectors_operations = connectors_subparsers.add_parser("operations")
    connectors_operations.add_argument("connector_id")
    connectors_subparsers.add_parser("auth-status")
    code_parser = subparsers.add_parser("code")
    code_subparsers = code_parser.add_subparsers(dest="code_command")
    code_subparsers.add_parser("scan")
    code_test = code_subparsers.add_parser("test")
    code_test.add_argument("test_command", nargs="?", default="")
    code_subparsers.add_parser("diff")
    code_subparsers.add_parser("status")
    code_patch = code_subparsers.add_parser("patch-plan")
    code_patch.add_argument("--problem", default="")
    code_patch.add_argument("--file", default="")
    code_patch.add_argument("--content", default="")
    code_commit = code_subparsers.add_parser("commit")
    code_commit.add_argument("message")
    code_commit.add_argument("--no-add-all", action="store_true")
    code_subparsers.add_parser("doctor")
    healing_parser = subparsers.add_parser("self-healing")
    healing_subparsers = healing_parser.add_subparsers(dest="self_healing_command")
    healing_subparsers.add_parser("status")
    healing_test = healing_subparsers.add_parser("test")
    healing_test.add_argument("error", nargs="?", default="command not found: npm")
    memory_parser = subparsers.add_parser("memory")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    memory_list = memory_subparsers.add_parser("list")
    memory_list.add_argument("--scope", default=None)
    memory_list.add_argument("--project", default=None)
    memory_list.add_argument("--status", default="active")
    memory_search = memory_subparsers.add_parser("search")
    memory_search.add_argument("query", nargs="?", default="")
    memory_search.add_argument("--scope", default=None)
    memory_search.add_argument("--project", default=None)
    memory_add = memory_subparsers.add_parser("add")
    memory_add.add_argument("--scope", default="project")
    memory_add.add_argument("--content", required=True)
    memory_add.add_argument("--type", default="fact")
    memory_add.add_argument("--key", default="")
    memory_add.add_argument("--project", default=None)
    memory_add.add_argument("--tags", default="")
    memory_delete = memory_subparsers.add_parser("delete")
    memory_delete.add_argument("memory_id")
    memory_subparsers.add_parser("suggestions")
    memory_accept = memory_subparsers.add_parser("accept")
    memory_accept.add_argument("suggestion_id")
    memory_reject = memory_subparsers.add_parser("reject")
    memory_reject.add_argument("suggestion_id")
    memory_compact = memory_subparsers.add_parser("compact")
    memory_compact.add_argument("--project", required=True)
    decisions_parser = subparsers.add_parser("decisions")
    decisions_subparsers = decisions_parser.add_subparsers(dest="decisions_command")
    decisions_list = decisions_subparsers.add_parser("list")
    decisions_list.add_argument("--project", default=None)
    decisions_add = decisions_subparsers.add_parser("add")
    decisions_add.add_argument("title")
    decisions_add.add_argument("content")
    decisions_add.add_argument("--reason", default="")
    decisions_add.add_argument("--project", default=None)
    decisions_archive = decisions_subparsers.add_parser("archive")
    decisions_archive.add_argument("decision_id")
    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("path")
    config_init = config_subparsers.add_parser("init")
    config_init.add_argument("--force", action="store_true")
    config_subparsers.add_parser("show")
    config_show_raw = config_subparsers.add_parser("show-raw")
    config_show_raw.add_argument("--raw", action="store_true")
    config_show = config_subparsers.choices["show"]
    config_show.add_argument("--raw", action="store_true")
    config_get = config_subparsers.add_parser("get")
    config_get.add_argument("path")
    config_set = config_subparsers.add_parser("set")
    config_set.add_argument("path")
    config_set.add_argument("value")
    config_unset = config_subparsers.add_parser("unset")
    config_unset.add_argument("path")
    config_migrate = config_subparsers.add_parser("migrate-env")
    config_migrate.add_argument("--force", action="store_true")
    config_subparsers.add_parser("doctor")
    secrets_parser = subparsers.add_parser("secrets")
    secrets_subparsers = secrets_parser.add_subparsers(dest="secrets_command")
    secrets_subparsers.add_parser("status")
    secrets_set_env = secrets_subparsers.add_parser("set-env")
    secrets_set_env.add_argument("name")
    secrets_set_env.add_argument("value")
    security_parser = subparsers.add_parser("security")
    security_subparsers = security_parser.add_subparsers(dest="security_command")
    security_audit = security_subparsers.add_parser("audit")
    security_audit.add_argument("--json", action="store_true", dest="json_output")
    security_audit.add_argument("--fix-safe", action="store_true")
    args = parser.parse_args(argv)

    if args.command in {None, "serve"}:
        with runtime_context("server"):
            return _serve_command(args)
    with runtime_context("cli"):
        return _dispatch_cli_command(args)


def run() -> None:
    exit_code = main()
    if exit_code:
        raise SystemExit(exit_code)


def _serve_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .gateway.server import serve_gateway

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    host = getattr(args, "host", None) or config.host
    port = getattr(args, "port", None) or config.port
    open_browser = args.command is None and config.open_browser and not getattr(args, "no_open", False)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        console.print("[bold yellow]Avertissement sécurité:[/bold yellow] Omega Gateway sera accessible hors boucle locale. N'utilisez cela que sur un réseau de confiance.")
    try:
        serve_gateway(config, host=host, port=port, open_browser=open_browser, reuse_existing=args.command is None)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    return 0


def _dispatch_cli_command(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        return doctor_command()
    if args.command == "chat":
        asyncio.run(chat_loop())
        return 0
    if args.command == "ui" and args.ui_command == "dev":
        return ui_dev_command()
    handlers = {
        "skills": skills_command,
        "budgets": budgets_command,
        "shadow": shadow_command,
        "plugins": plugins_command,
        "tools": tools_command,
        "workspace": workspace_command,
        "mobile": mobile_command,
        "models": models_command,
        "jobs": jobs_command,
        "runs": runs_command,
        "rollback": rollback_command,
        "runtime": runtime_command,
        "workflows": workflows_command,
        "evals": evals_command,
        "traces": traces_command,
        "events": events_command,
        "research": research_command,
        "policy": policy_command,
        "capabilities": capabilities_command,
        "mcp": mcp_command,
        "a2a": a2a_command,
        "connectors": connectors_command,
        "code": code_command,
        "self-healing": self_healing_command,
        "memory": memory_command,
        "decisions": decisions_command,
        "config": config_command,
        "secrets": secrets_command,
        "security": security_command,
    }
    handler = handlers.get(args.command)
    if handler is not None:
        return handler(args)
    console.print("Commande inconnue. Commandes: serve, chat, doctor, ui, skills, plugins, tools, workspace, security")
    return 2


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
    from .config import OmegaConfig
    from .runtime.skills_registry import SkillsRegistry
    from .skills.foundry import SkillFoundry
    from .skills.skill_promoter import SkillPromoter
    from .skills.skill_store import SkillStore
    from .skills.skill_usage import SkillUsageStore

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    registry = SkillsRegistry(config)
    store = SkillStore(config)
    promoter = SkillPromoter(config)
    if args.skills_command == "list":
        for skill in registry.list():
            console.print(f"{skill.id}  {skill.name}  {skill.status}  v{skill.version}  {skill.risk_level} - {skill.description}")
        return 0
    if args.skills_command == "show":
        skill = store.get_skill(args.skill_id)
        if skill is None:
            legacy = next((item for item in registry.list() if item.id == args.skill_id or item.name == args.skill_id), None)
            if legacy is None:
                console.print("[red]Skill introuvable.[/red]")
                return 1
            console.print_json(json.dumps(legacy.__dict__, ensure_ascii=False, default=str))
            return 0
        payload = {
            "skill": skill.as_api(),
            "versions": [item.as_api() for item in store.list_versions(skill.id)],
            "tests": [item.as_api() for item in store.list_test_runs(skill.id)],
            "usage": SkillUsageStore(config).summary(skill.id),
        }
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return 0
    if args.skills_command == "candidates":
        candidates = store.list_candidates()
        if not candidates:
            console.print("Aucune candidate.")
        for candidate in candidates:
            console.print(f"{candidate.id}  {candidate.status}  {candidate.confidence:.2f}  {candidate.title}")
        return 0
    if args.skills_command == "detect":
        candidates = SkillFoundry(config).detect_candidates()
        console.print(f"{len(candidates)} candidate(s) détectée(s).")
        for candidate in candidates:
            console.print(f"{candidate.id}  {candidate.confidence:.2f}  {candidate.title}")
        return 0
    if args.skills_command == "accept":
        try:
            skill = promoter.accept_candidate(args.candidate_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Draft créée: {skill.id}  {skill.name}  v{skill.version}")
        return 0
    if args.skills_command == "reject":
        try:
            candidate = promoter.reject_candidate(args.candidate_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Candidate rejetée: {candidate.id}")
        return 0
    if args.skills_command == "test":
        try:
            result = promoter.test_skill(args.skill_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"{result.status}: {result.skill_id} v{result.version}")
        return 0 if result.status == "passed" else 1
    if args.skills_command == "activate":
        try:
            skill = promoter.activate(args.skill_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Skill active: {skill.id}  {skill.name}")
        return 0
    if args.skills_command == "disable":
        try:
            skill = promoter.disable(args.skill_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Skill disabled: {skill.id}  {skill.name}")
        return 0
    if args.skills_command == "create":
        skill = registry.create(args.name, args.description, risk=args.risk)
        console.print(f"Skill créée: {skill.path}")
        return 0
    console.print("Commandes: omega skills list|show|candidates|detect|accept|reject|test|activate|disable|create")
    return 2


def budgets_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .governance.budget_enforcer import BudgetEnforcer
    from .governance.budget_store import BudgetStore
    from .governance.quota_tracker import QuotaTracker

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    store = BudgetStore(config)
    enforcer = BudgetEnforcer(config)
    if args.budgets_command == "profiles":
        for profile in store.list_profiles():
            marker = "enabled" if profile.enabled else "disabled"
            scope = f"{profile.scope_type}:{profile.scope_id}" if profile.scope_id else profile.scope_type
            console.print(f"{profile.id}  {profile.name}  {marker}  {scope}")
        return 0
    if args.budgets_command == "show":
        profile = store.get_profile(args.profile_id)
        if profile is None:
            console.print("[red]Budget profile introuvable.[/red]")
            return 1
        console.print_json(json.dumps(profile.as_api(), ensure_ascii=False))
        return 0
    if args.budgets_command == "usage":
        items = QuotaTracker(config).list()
        if not items:
            console.print("Aucun usage budget.")
        for item in items:
            limit = "unlimited" if item.limit_value is None else f"{item.limit_value:g}"
            console.print(f"{item.metric}  {item.used_value:g}/{limit}  {item.status}  run={item.run_id or '-'}")
        return 0
    if args.budgets_command == "violations":
        items = store.list_violations()
        if not items:
            console.print("Aucune violation budget.")
        for item in items:
            console.print(f"{item.created_at}  {item.metric}  {item.used_value:g}>{item.limit_value:g}  {item.action_taken}  {item.reason}")
        return 0
    if args.budgets_command == "simulate":
        context = enforcer.context(run_id=args.run)
        decision = enforcer.check_before_action(
            context,
            {"tool_name": args.tool, "risk_level": args.risk, "action_category": args.category, "arguments": {}, "simulate": True},
        )
        console.print_json(json.dumps({"decision": decision.as_api(), "effective_budget": enforcer.get_effective_budget(context).as_api()}, ensure_ascii=False))
        return 0 if decision.action in {"allow", "warn"} else 1
    if args.budgets_command == "doctor":
        errors = []
        if not config.governance_budgets_enabled:
            errors.append("Budgets disabled.")
        if not config.governance_budgets_enforce:
            errors.append("Budget enforcement disabled.")
        default_profile = store.get_profile(config.governance_budgets_default_profile)
        if default_profile is None:
            errors.append("Default budget profile missing.")
        elif not default_profile.enabled:
            errors.append("Default budget profile disabled.")
        if config.governance_risk_governor_default_max_risk == "critical":
            errors.append("Global maximum risk is critical.")
        if errors:
            for error in errors:
                console.print(f"[red]FAIL[/red] {error}")
            return 1
        effective = enforcer.get_effective_budget(enforcer.context())
        console.print(f"[green]OK[/green] budgets enabled and enforced; default={config.governance_budgets_default_profile}; max_risk={effective.limits.get('max_risk_level')}")
        return 0
    console.print("Commandes: omega budgets profiles|show|usage|violations|simulate|doctor")
    return 2


def shadow_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .shadow.shadow_runner import ShadowRunner

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    runner = ShadowRunner(config)
    try:
        if args.shadow_command == "create":
            item = runner.create_shadow_run(args.objective)
            console.print(f"{item['id']}  {item['status']}  {item['objective']}")
            return 0
        if args.shadow_command == "run":
            item = runner.run_shadow(args.shadow_run_id)
            console.print_json(json.dumps(item, ensure_ascii=False))
            return 0 if item["status"] == "succeeded" else 1
        if args.shadow_command == "show":
            item = runner.get_shadow_run(args.shadow_run_id)
            if item is None:
                console.print("[red]Shadow run introuvable.[/red]")
                return 1
            console.print_json(json.dumps(item, ensure_ascii=False))
            return 0
        if args.shadow_command == "diff":
            item = runner.require_shadow_run(args.shadow_run_id)
            console.print_json(json.dumps(item.get("predicted_diff") or runner.collect_predicted_diff(args.shadow_run_id), ensure_ascii=False))
            return 0
        if args.shadow_command == "risk":
            item = runner.require_shadow_run(args.shadow_run_id)
            console.print_json(json.dumps(item.get("risk_report") or runner.compute_risk_report(args.shadow_run_id), ensure_ascii=False))
            return 0
        if args.shadow_command == "promote":
            result = runner.promote_to_live(args.shadow_run_id, approved_by=args.approved_by)
            console.print_json(json.dumps(result, ensure_ascii=False))
            return 0 if not result.get("approval_required") else 1
        if args.shadow_command == "reject":
            item = runner.reject(args.shadow_run_id)
            console.print(f"{item['id']}  {item['status']}")
            return 0
        if args.shadow_command == "list":
            for item in runner.list_shadow_runs():
                risk = (item.get("risk_report") or {}).get("risk_level") or "-"
                recommendation = (item.get("risk_report") or {}).get("recommendation") or "-"
                console.print(f"{item['id']}  {item['status']}  risk={risk}  recommendation={recommendation}  {item['objective']}")
            return 0
    except (ValueError, PermissionError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    console.print("Commandes: omega shadow create|run|show|diff|risk|promote|reject|list")
    return 2


def plugins_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.plugins_registry import PluginsRegistry

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if args.plugins_command == "list":
        for plugin in PluginsRegistry(config).list():
            console.print(f"{plugin.name} ({plugin.status}) - {plugin.path}")
        return 0
    console.print("Commandes: omega plugins list")
    return 2


def tools_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.tool_broker import ToolBroker
    from .runtime.tools_registry import list_tools

    if args.tools_command == "list":
        for tool in list_tools():
            marker = "approval" if tool.requires_approval else "direct"
            console.print(f"{tool.id} ({tool.risk}/{marker}) {tool.description}")
        return 0
    if args.tools_command == "test":
        config = OmegaConfig.from_env()
        broker = ToolBroker(config)
        if args.test_name == "write-file":
            result = broker.call("write_file", {"relative_path": ".omega-tool-test.txt", "content": "Omega tool test\n"})
            target = config.workspace / ".omega-tool-test.txt"
            if result.status != "completed" or not target.exists():
                console.print(f"[red]FAIL[/red] write_file: {result.output}")
                return 1
            if config.allow_delete_in_workspace:
                delete_result = broker.call("delete_file", {"relative_path": ".omega-tool-test.txt"})
                if delete_result.status != "completed" or target.exists():
                    console.print(f"[red]FAIL[/red] delete_file: {delete_result.output}")
                    return 1
            console.print("[green]OK[/green] write-file")
            return 0
        if args.test_name == "shell":
            command = "cmd /c dir" if sys.platform == "win32" else "ls"
            result = broker.call("run_shell", {"command": command})
            if result.status != "completed":
                console.print(f"[red]FAIL[/red] shell: {result.output}")
                return 1
            console.print("[green]OK[/green] shell")
            console.print(result.output[:1000])
            return 0
    console.print("Commandes: omega tools list|test write-file|test shell")
    return 2


def workspace_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig

    config = OmegaConfig.from_env()
    if args.workspace_command == "doctor":
        checks = [
            ("Workspace exists", config.workspace.exists() and config.workspace.is_dir(), str(config.workspace)),
            ("Workspace writable", _workspace_writable(config), str(config.workspace)),
            ("Workspace full access", config.workspace_full_access, "active" if config.workspace_full_access else "inactive"),
            ("Approval inside workspace", True, "disabled" if config.workspace_full_access else "enabled"),
            ("Outside workspace", True, "denied"),
            ("Shell inside workspace", config.shell_full_access_in_workspace, "enabled" if config.shell_full_access_in_workspace else "disabled"),
            ("Delete inside workspace", config.allow_delete_in_workspace, "enabled" if config.allow_delete_in_workspace else "disabled"),
        ]
        failed = False
        for name, ok, detail in checks:
            console.print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
            failed = failed or not ok
        return 1 if failed else 0
    console.print("Commandes: omega workspace doctor")
    return 2


def mobile_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig

    config = OmegaConfig.from_env()
    if args.mobile_command == "tailscale":
        if args.tailscale_command == "status":
            return _print_tailscale_result(tailscale_status(config))
        if args.tailscale_command == "serve":
            if config.mobile_mode != "tailscale":
                console.print("[yellow]mobile.mode n'est pas tailscale; commande lancee explicitement quand meme.[/yellow]")
            return _print_tailscale_result(tailscale_serve(config))
        if args.tailscale_command == "stop":
            return _print_tailscale_result(tailscale_stop(config))
        if args.tailscale_command == "url":
            return _print_tailscale_result(tailscale_url(config))
    console.print("Commandes: omega mobile tailscale status|serve|stop|url")
    return 2


def tailscale_status(config):
    from .mobile import tailscale_status as status

    return status(config)


def tailscale_serve(config):
    from .mobile import tailscale_serve as serve

    return serve(config)


def tailscale_stop(config):
    from .mobile import tailscale_stop as stop

    return stop(config)


def tailscale_url(config):
    from .mobile import tailscale_url as url

    return url(config)


def _print_tailscale_result(result) -> int:
    color = "green" if result.ok else "red"
    marker = "OK" if result.ok else "FAIL"
    console.print(f"[{color}]{marker}[/{color}] {result.message}")
    if result.url and result.url not in result.message:
        console.print(result.url)
    if result.ok:
        console.print("Mobile: Tailscale Serve reste limite au tailnet. N'active pas Funnel sauf confirmation explicite.")
    return 0 if result.ok else 1


def _workspace_writable(config: OmegaConfig) -> bool:
    try:
        config.ensure_dirs()
        target = config.workspace / ".omega-workspace-doctor.tmp"
        target.write_text("ok", encoding="utf-8")
        target.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def models_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.model_selector import ModelSelector

    _load_legacy_dotenv_if_needed()
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
    if args.models_command == "set-default":
        preference = selector.set_preference("global", args.model_ref)
        console.print(f"Default model: {preference.primary_model_ref}")
        return 0
    if args.models_command == "set-fallback":
        preference = selector.set_preference("global", config.default_model_ref, fallback_model_ref=args.model_ref)
        console.print(f"Fallback model: {preference.fallback_model_ref}")
        return 0
    if args.models_command == "enable-provider":
        _set_provider_config_enabled(args.provider, True)
        console.print(f"Provider active: {args.provider}")
        return 0
    if args.models_command == "disable-provider":
        _set_provider_config_enabled(args.provider, False)
        console.print(f"Provider desactive: {args.provider}")
        return 0
    if args.models_command == "set-provider-base-url":
        _set_provider_base_url(args.provider, args.url)
        console.print(f"Base URL {args.provider}: {args.url}")
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
    from .config import OmegaConfig
    from .runtime.jobs import JobsStore

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if args.jobs_command == "list":
        for job in JobsStore(config).list():
            console.print(f"{job.id} {job.status} {job.kind} - {job.title}")
        return 0
    console.print("Commandes: omega jobs list")
    return 2


def runs_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .evals.run_scoring import RunScoring
    from .evals.task_outcomes import TaskOutcomesStore
    from .runtime.durable_runtime import DurableRuntime

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    runtime = DurableRuntime(config)
    if args.runs_command == "list":
        for run in runtime.list_runs(limit=50):
            console.print(f"{run.id} {run.status} {run.updated_at} - {run.title}")
        return 0
    if args.runs_command == "show":
        run = runtime.get_run(args.run_id)
        if run is None:
            console.print("[red]Run introuvable.[/red]")
            return 1
        console.print(json.dumps(run.as_api(), ensure_ascii=False, indent=2))
        for step in runtime.list_steps(args.run_id):
            console.print(f"STEP {step.step_index} {step.status} {step.type}: {step.title}")
        for action in runtime.list_actions(args.run_id):
            console.print(f"ACTION {action.status} {action.tool_name} rollback={str(action.rollback_available).lower()}")
        return 0
    if args.runs_command == "resume":
        console.print(json.dumps(runtime.resume_run(args.run_id).as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.runs_command == "cancel":
        console.print(json.dumps(runtime.cancel_run(args.run_id).as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.runs_command == "replay":
        console.print(json.dumps(runtime.replay_run(args.run_id, dry_run=True), ensure_ascii=False, indent=2))
        return 0
    if args.runs_command == "score":
        console.print(json.dumps(RunScoring(config).score_run(args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.runs_command == "outcome":
        outcome = TaskOutcomesStore(config).update_outcome(args.run_id, args.outcome, reason="CLI user outcome")
        console.print(json.dumps(outcome.as_api(), ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega runs list|show <run_id>|resume <run_id>|cancel <run_id>|replay <run_id>|score <run_id>|outcome <run_id> <outcome>")
    return 2


def rollback_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.durable_runtime import DurableRuntime

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    runtime = DurableRuntime(config)
    if args.rollback_command == "list":
        for snapshot in runtime.list_snapshots(limit=100):
            restored = "restored" if snapshot.restored_at else "available"
            console.print(f"{snapshot.id} {restored} {snapshot.workspace_path} run={snapshot.run_id} existed={str(snapshot.existed_before).lower()}")
        return 0
    if args.rollback_command == "run":
        console.print(json.dumps(runtime.rollback_run(args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.rollback_command == "snapshot":
        console.print(json.dumps(runtime.rollback_snapshot(args.snapshot_id), ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega rollback list|run <run_id>|snapshot <snapshot_id>")
    return 2


def runtime_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.durable_runtime import DurableRuntime
    from .runtime.storage import connect_runtime_db

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if args.runtime_command == "doctor":
        config.ensure_dirs()
        runtime = DurableRuntime(config)
        required_tables = {
            "runs",
            "run_steps",
            "checkpoints",
            "action_journal",
            "file_snapshots",
            "rollback_events",
            "dead_letter_runs",
            "eval_runs",
            "eval_cases",
            "task_outcomes",
            "run_metrics",
            "failure_clusters",
        }
        with connect_runtime_db(config) as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        snapshots_dir = config.workspace / ".omega" / "snapshots"
        checks = [
            ("DB runtime tables", required_tables.issubset(tables), ", ".join(sorted(required_tables - tables)) or "present"),
            ("Snapshots dir", snapshots_dir.parent.exists(), str(snapshots_dir)),
            ("Checkpoints enabled", config.runtime_checkpoints_enabled, str(config.runtime_checkpoints_enabled).lower()),
            ("Snapshots enabled", config.runtime_snapshots_enabled, str(config.runtime_snapshots_enabled).lower()),
            ("Replay enabled", config.runtime_replay_enabled, str(config.runtime_replay_enabled).lower()),
            ("Workspace rollback safe", True, str(config.workspace)),
            ("Recoverable runs", True, str(len(runtime.list_runs(status="paused", limit=100)))),
            ("Action journal", "action_journal" in tables, "present" if "action_journal" in tables else "missing"),
        ]
        failed = False
        for name, ok, detail in checks:
            console.print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
            failed = failed or not ok
        return 1 if failed else 0
    console.print("Commandes: omega runtime doctor")
    return 2


def workflows_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .workflows.workflow_parser import load_workflow_file
    from .workflows.workflow_runner import WorkflowRunner
    from .workflows.workflow_store import WorkflowStore

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if not config.workflows_enabled:
        console.print("[red]Workflows desactives par configuration.[/red]")
        return 1
    store = WorkflowStore(config)
    runner = WorkflowRunner(config)
    if args.workflows_command == "templates":
        for template in store.list_templates():
            console.print(f"{template.id} [{template.category}] - {template.name}: {template.description}", markup=False)
        return 0
    if args.workflows_command == "list":
        workflows = store.list_workflows(limit=100)
        if not workflows:
            console.print("Aucun workflow.")
        for workflow in workflows:
            enabled = "enabled" if workflow.enabled else "disabled"
            console.print(f"{workflow.id} {enabled} v{workflow.version} - {workflow.name}", markup=False)
        return 0
    if args.workflows_command == "create":
        try:
            if args.file:
                definition = load_workflow_file(args.file)
            elif args.template:
                template = store.get_template(args.template)
                if template is None:
                    console.print("[red]Template introuvable.[/red]")
                    return 1
                definition = template.definition
            else:
                definition = {
                    "name": args.name or "Manual Workflow",
                    "description": "Workflow manuel cree depuis la CLI.",
                    "version": "1.0",
                    "steps": [{"id": "final", "type": "final", "name": "Final", "message": "Workflow created."}],
                }
            if args.name:
                definition = {**definition, "name": args.name}
            workflow = runner.create_workflow(definition, metadata={"source": "cli"})
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(json.dumps(workflow.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.workflows_command == "show":
        workflow = _resolve_workflow_for_cli(store, " ".join(args.workflow))
        if workflow is None:
            console.print("[red]Workflow introuvable.[/red]")
            return 1
        payload = workflow.as_api()
        payload["recent_runs"] = [run.as_api() for run in store.list_runs(workflow_id=workflow.id, limit=10)]
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.workflows_command == "run":
        workflow = _resolve_workflow_or_template_for_cli(runner, store, " ".join(args.workflow))
        if workflow is None:
            console.print("[red]Workflow ou template introuvable.[/red]")
            return 1
        try:
            workflow_run = runner.run_workflow(workflow.id, input={})
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(json.dumps(runner.get_workflow_run_status(workflow_run.id), ensure_ascii=False, indent=2))
        return 0 if workflow_run.status in {"succeeded", "paused"} else 1
    if args.workflows_command == "runs":
        for workflow_run in store.list_runs(status=args.status, limit=100):
            console.print(f"{workflow_run.id} {workflow_run.status} workflow={workflow_run.workflow_id} run={workflow_run.run_id or '-'} step={workflow_run.current_step_index}", markup=False)
        return 0
    if args.workflows_command == "status":
        try:
            console.print(json.dumps(runner.get_workflow_run_status(args.workflow_run_id), ensure_ascii=False, indent=2))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        return 0
    if args.workflows_command == "pause":
        try:
            console.print(json.dumps(runner.pause_workflow_run(args.workflow_run_id).as_api(), ensure_ascii=False, indent=2))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        return 0
    if args.workflows_command == "resume":
        try:
            console.print(json.dumps(runner.resume_workflow_run(args.workflow_run_id).as_api(), ensure_ascii=False, indent=2))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        return 0
    if args.workflows_command == "cancel":
        try:
            console.print(json.dumps(runner.cancel_workflow_run(args.workflow_run_id).as_api(), ensure_ascii=False, indent=2))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        return 0
    if args.workflows_command == "retry-step":
        try:
            console.print(json.dumps(runner.retry_step(args.workflow_run_id, args.step_id).as_api(), ensure_ascii=False, indent=2))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        return 0
    console.print("Commandes: omega workflows list|templates|create|show <id>|run <id>|runs|status <run_id>|pause <run_id>|resume <run_id>|cancel <run_id>|retry-step <run_id> <step_id>")
    return 2


def _resolve_workflow_for_cli(store: WorkflowStore, identifier: str):
    return store.find_workflow(identifier.strip())


def _resolve_workflow_or_template_for_cli(runner: WorkflowRunner, store: WorkflowStore, identifier: str):
    workflow = _resolve_workflow_for_cli(store, identifier)
    if workflow is not None:
        return workflow
    template = store.get_template(identifier.strip())
    if template is None:
        return None
    return runner.create_workflow(template.definition, metadata={"source": "template", "template_id": template.id})


def evals_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .evals.eval_reports import EvalReports
    from .evals.eval_runner import EvalRunner, run_eval_dataset_sync
    from .evals.failure_clustering import FailureClustering
    from .evals.metrics import MetricsStore

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if not config.evals_enabled:
        console.print("[red]Evaluation Loop est desactive par configuration.[/red]")
        return 1
    runner = EvalRunner(config)
    if args.evals_command == "list":
        for item in runner.list_eval_runs():
            summary = item.get("summary") or {}
            console.print(f"{item['id']} {item['status']} {item.get('dataset_name') or ''} avg={summary.get('average_score', '')} - {item['name']}")
        return 0
    if args.evals_command == "run":
        console.print(json.dumps(run_eval_dataset_sync(config, args.dataset), ensure_ascii=False, indent=2))
        return 0
    if args.evals_command == "report":
        report = EvalReports(config)
        path = report.write_report()
        console.print(str(path))
        return 0
    if args.evals_command == "failures":
        console.print(json.dumps(FailureClustering(config).cluster_recent_failures(), ensure_ascii=False, indent=2))
        return 0
    if args.evals_command == "metrics":
        metrics = MetricsStore(config)
        payload = {
            "aggregate": metrics.aggregate_metrics(),
            "models": metrics.model_performance_summary(),
            "tools": metrics.tool_reliability_summary(),
            "agents": metrics.agent_profile_performance_summary(),
            "policy": metrics.policy_friction_summary(),
        }
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega evals list|run <dataset>|report|failures|metrics")
    return 2


def traces_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .evals.failure_clustering import FailureClustering
    from .evals.metrics import MetricsStore
    from .evals.trace_collector import TraceCollector

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    collector = TraceCollector(config)
    if args.traces_command == "list":
        for item in collector.list_traces(limit=100):
            metrics = item.get("metrics") or {}
            console.print(f"{item['run_id']} {item['status']} tools={metrics.get('tool_calls_count', 0)} updated={item['updated_at']} - {item['title']}")
        return 0
    if args.traces_command == "show":
        console.print(json.dumps(collector.collect_run_trace(args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.traces_command == "export":
        console.print(collector.export_trace_json(args.run_id), markup=False)
        return 0
    if args.traces_command == "analyze":
        metrics = MetricsStore(config)
        payload = {
            "metrics": metrics.aggregate_metrics(),
            "failures": FailureClustering(config).cluster_recent_failures(),
        }
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega traces list|show <run_id>|export <run_id>|analyze")
    return 2


def events_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .events import EventBus, EventStore

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    store = EventStore(config)
    if args.events_command == "list":
        events = store.list(limit=args.limit, type=args.type, run_id=args.run_id, for_ui=True)
        if not events:
            console.print("Aucun event.")
        for event in events:
            session = f" session={event.session_id}" if event.session_id else ""
            run = f" run={event.run_id}" if event.run_id else ""
            console.print(f"{event.id} {event.timestamp} {event.level} {event.source} {event.type}{session}{run}", markup=False)
        return 0
    if args.events_command == "show":
        event = store.get(args.event_id, for_ui=True)
        if event is None:
            console.print("[red]Event introuvable.[/red]")
            return 1
        console.print(json.dumps(event.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.events_command == "replay":
        events = EventBus(config).replay_events(
            since_id=args.since_id,
            session_id=args.session_id,
            run_id=args.run_id,
            limit=args.limit,
        )
        for event in events:
            console.print(json.dumps(event.as_api(), ensure_ascii=False), markup=False)
        return 0
    if args.events_command == "tail":
        for event in store.list(limit=args.limit, for_ui=True):
            console.print(f"{event.timestamp} {event.level} {event.type} {json.dumps(event.payload, ensure_ascii=False)}", markup=False)
        return 0
    if args.events_command == "types":
        for event_type in store.types():
            console.print(event_type, markup=False)
        return 0
    console.print("Commandes: omega events list|show <id>|replay [--run <run_id>]|tail|types")
    return 2


def research_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .research.research_agent import OmegaResearchAgent

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    agent = OmegaResearchAgent(config)
    try:
        if args.research_command == "start":
            run = agent.start(args.question, title=args.title)
            console.print(f"Research completed: {run.id} [{run.status}]", markup=False)
            console.print(run.report_markdown or "Aucun rapport.", markup=False)
            return 0
        if args.research_command == "list":
            runs = agent.repository.list_runs()
            if not runs:
                console.print("Aucun research run.")
            for run in runs:
                console.print(f"{run.id} [{run.status}] {run.title}", markup=False)
            return 0
        if args.research_command == "show":
            console.print(json.dumps(agent.detail(args.research_run_id), ensure_ascii=False, indent=2))
            return 0
        if args.research_command == "export":
            result = agent.export(args.research_run_id, args.format)
            console.print(f"Export {result['format']}: {result['path']}", markup=False)
            return 0
        if args.research_command == "sources":
            agent.repository.require_run(args.research_run_id)
            for source in agent.repository.list_sources(args.research_run_id):
                console.print(
                    f"{source.id} [{source.source_type}/{source.trust_level}] {source.title} - {source.locator or source.uri or 'sans locator'}",
                    markup=False,
                )
            return 0
        if args.research_command == "claims":
            agent.repository.require_run(args.research_run_id)
            for claim in agent.repository.list_claims(args.research_run_id):
                console.print(f"{claim.id} [{claim.status} {claim.confidence:.0%}] {claim.claim_text}", markup=False)
            return 0
    except PermissionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    console.print("Commandes: omega research start <question>|list|show <id>|export <id> --format markdown|sources <id>|claims <id>")
    return 2


def policy_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .security.audit import run_security_audit
    from .security.policy_profiles import PolicyProfilesStore, PolicyRulesStore
    from .security.policy_simulator import PolicySimulator

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    profiles = PolicyProfilesStore(config)
    rules = PolicyRulesStore(config)
    if args.policy_command == "profiles":
        for profile in profiles.list():
            enabled = "enabled" if profile.enabled else "disabled"
            console.print(f"{profile.id} {enabled} priority={profile.priority} scope={profile.scope_type}:{profile.scope_id or '*'} default={profile.default_action} - {profile.name}")
        return 0
    if args.policy_command == "rules":
        for rule in rules.list():
            enabled = "enabled" if rule.enabled else "disabled"
            console.print(f"{rule.id} {enabled} {rule.effect} priority={rule.priority} profile={rule.profile_id} tool={rule.tool_name or '*'} - {rule.name}")
        return 0
    if args.policy_command == "show":
        profile = profiles.get(args.profile_id)
        if profile is None:
            console.print("[red]Policy profile introuvable.[/red]")
            return 1
        payload = profile.as_api()
        payload["rules"] = [rule.as_api() for rule in rules.list(profile_id=args.profile_id)]
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.policy_command in {"enable", "disable"}:
        try:
            profile = profiles.patch(args.profile_id, {"enabled": args.policy_command == "enable"})
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"{args.policy_command}d {profile.id}")
        return 0
    if args.policy_command == "add-rule":
        conditions = _parse_policy_conditions(args.condition)
        try:
            rule = rules.create(
                profile_id=args.profile,
                name=args.name,
                effect=args.effect,
                tool_name=args.tool,
                action_type=args.action_type,
                resource_pattern=args.resource,
                risk_level_min=args.risk_min,
                conditions=conditions,
                priority=args.priority,
                reason=args.reason,
            )
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(json.dumps(rule.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.policy_command == "simulate":
        arguments: dict[str, object] = {}
        if args.path:
            arguments["relative_path"] = args.path
        if args.shell_command:
            arguments["command"] = args.shell_command
        if args.file_count:
            arguments["file_count"] = args.file_count
        payload = {
            "tool_name": args.tool,
            "arguments": arguments,
            "channel": args.channel,
            "source_trust": args.source_trust,
            "agent_profile_id": args.agent_profile,
            "file_count": args.file_count,
        }
        console.print(json.dumps(PolicySimulator(config).simulate_policy(payload), ensure_ascii=False, indent=2))
        return 0
    if args.policy_command == "doctor":
        report = run_security_audit(config).as_api()
        findings = [item for item in report["findings"] if item.get("area") == "policy"]
        for finding in findings:
            console.print(f"{finding['severity'].upper()} policy: {finding['finding']} -> {finding['recommendation']}")
        console.print(f"Policy findings: {len(findings)}")
        return 1 if any(item["severity"] in {"critical", "high"} for item in findings) else 0
    console.print("Commandes: omega policy profiles|rules|show|enable|disable|add-rule|simulate|doctor")
    return 2


def _parse_policy_conditions(items: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items or []:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.lower() in {"true", "false"}:
            result[key] = value.lower() == "true"
        else:
            try:
                result[key] = int(value)
            except ValueError:
                if "," in value:
                    result[key] = [part.strip() for part in value.split(",") if part.strip()]
                else:
                    result[key] = value
    return result


def capabilities_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.capabilities import CapabilitiesRegistry

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    registry = CapabilitiesRegistry(config)
    if args.capabilities_command == "list":
        for capability in registry.list():
            enabled = "enabled" if capability.enabled else "disabled"
            console.print(f"{capability.id} {enabled} {capability.risk_level} - {capability.name}")
        return 0
    if args.capabilities_command == "show":
        capability = registry.get(args.capability_id)
        if capability is None:
            console.print("[red]Capability introuvable.[/red]")
            return 1
        console.print(json.dumps(capability.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.capabilities_command == "enable":
        capability = registry.enable(args.capability_id)
        if capability is None:
            console.print("[red]Capability introuvable.[/red]")
            return 1
        console.print(f"enabled {capability.id}")
        return 0
    if args.capabilities_command == "disable":
        capability = registry.disable(args.capability_id)
        if capability is None:
            console.print("[red]Capability introuvable.[/red]")
            return 1
        console.print(f"disabled {capability.id}")
        return 0
    if args.capabilities_command == "refresh":
        console.print(json.dumps(registry.refresh(), ensure_ascii=False, indent=2))
        return 0
    if args.capabilities_command == "search":
        for capability in registry.search(args.query):
            enabled = "enabled" if capability.enabled else "disabled"
            console.print(f"{capability.id} {enabled} {capability.risk_level} - {capability.name}")
        return 0
    console.print("Commandes: omega capabilities list|show|enable|disable|refresh|search")
    return 2


def mcp_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.capabilities import CapabilitiesRegistry
    from .runtime.mcp_servers import MCPServersRegistry

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    registry = MCPServersRegistry(config)
    if args.mcp_command == "list":
        for server in registry.list():
            enabled = "enabled" if server.enabled else "disabled"
            console.print(f"{server.id} {enabled} {server.trust_level} {server.status} - {server.name}")
        return 0
    if args.mcp_command == "add":
        try:
            server = registry.add(name=args.name, url=args.url, command=args.command)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(json.dumps(server.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.mcp_command in {"enable", "disable"}:
        server = registry.patch(args.server_id, {"enabled": args.mcp_command == "enable"})
        if server is None:
            console.print("[red]MCP server introuvable.[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(f"{args.mcp_command}d {server.id}")
        return 0
    if args.mcp_command == "status":
        console.print(f"MCP execution enabled: {str(config.capabilities_mcp_enabled).lower()} (v1 manifest-only)")
        console.print(f"Servers: {len(registry.list())}")
        return 0
    console.print("Commandes: omega mcp list|add|enable|disable|status")
    return 2


def a2a_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.a2a_agents import A2AAgentsRegistry
    from .runtime.capabilities import CapabilitiesRegistry

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    registry = A2AAgentsRegistry(config)
    if args.a2a_command == "list":
        for agent in registry.list():
            enabled = "enabled" if agent.enabled else "disabled"
            console.print(f"{agent.id} {enabled} {agent.trust_level} {agent.status} - {agent.name}")
        return 0
    if args.a2a_command == "add":
        try:
            agent = registry.add(name=args.name, endpoint=args.endpoint)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(json.dumps(agent.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.a2a_command in {"enable", "disable"}:
        agent = registry.patch(args.agent_id, {"enabled": args.a2a_command == "enable"})
        if agent is None:
            console.print("[red]A2A agent introuvable.[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(f"{args.a2a_command}d {agent.id}")
        return 0
    if args.a2a_command == "status":
        console.print(f"A2A execution enabled: {str(config.capabilities_a2a_enabled).lower()} (v1 manifest-only)")
        console.print(f"Agents: {len(registry.list())}")
        return 0
    console.print("Commandes: omega a2a list|add|enable|disable|status")
    return 2


def connectors_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .connectors.registry import ConnectorsRegistry
    from .runtime.capabilities import CapabilitiesRegistry

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    registry = ConnectorsRegistry(config)
    if args.connectors_command == "list":
        connectors = registry.list()
        if not connectors:
            console.print("Aucun connecteur.")
        for connector in connectors:
            enabled = "enabled" if connector.enabled else "disabled"
            console.print(f"{connector.id} {enabled} {connector.type} {connector.trust_level} {connector.status} ops={len(connector.operations)} - {connector.name}", markup=False)
        return 0
    if args.connectors_command == "show":
        connector = registry.get(args.connector_id)
        if connector is None:
            console.print("[red]Connecteur introuvable.[/red]")
            return 1
        console.print(json.dumps(connector.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.connectors_command in {"enable", "disable"}:
        connector = registry.enable(args.connector_id) if args.connectors_command == "enable" else registry.disable(args.connector_id)
        if connector is None:
            console.print("[red]Connecteur introuvable.[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(f"{args.connectors_command}d {connector.id}", markup=False)
        return 0
    if args.connectors_command == "test":
        try:
            console.print(json.dumps(registry.test_connector(args.connector_id), ensure_ascii=False, indent=2))
        except KeyError:
            console.print("[red]Connecteur introuvable.[/red]")
            return 1
        return 0
    if args.connectors_command == "import-openapi":
        try:
            import_path = _resolve_connector_import_path(config, args.path)
            connector = registry.import_openapi(import_path, name=args.name, base_url=args.base_url, trust_level=args.trust_level, source=str(import_path))
        except (PermissionError, ValueError, OSError) as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        CapabilitiesRegistry(config).refresh()
        console.print(json.dumps(connector.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.connectors_command == "operations":
        connector = registry.get(args.connector_id)
        if connector is None:
            console.print("[red]Connecteur introuvable.[/red]")
            return 1
        for operation in registry.operations(args.connector_id):
            approval = "approval" if operation.requires_approval_default else "direct"
            console.print(f"{operation.id} {operation.action_category} {operation.risk_level}/{approval} - {operation.name}", markup=False)
        return 0
    if args.connectors_command == "auth-status":
        console.print(json.dumps(registry.auth_status(), ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega connectors list|show <id>|enable <id>|disable <id>|test <id>|import-openapi <path>|operations <id>|auth-status")
    return 2


def _resolve_connector_import_path(config: OmegaConfig, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute() or path.exists():
        return path.resolve()
    workspace_candidate = (config.workspace / value).resolve()
    if workspace_candidate.exists():
        return workspace_candidate
    return path.resolve()


def code_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.code_agent import CodeWorkspaceAgent

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    if not config.code_enabled:
        console.print("[red]Code Workspace est desactive par configuration.[/red]")
        return 1
    agent = CodeWorkspaceAgent(config)
    if args.code_command == "scan":
        console.print(json.dumps(agent.scan(), ensure_ascii=False, indent=2))
        return 0
    if args.code_command == "test":
        payload = agent.test(command=args.test_command.strip() or None)
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "passed" else 1
    if args.code_command == "diff":
        console.print(json.dumps(agent.diff(), ensure_ascii=False, indent=2))
        return 0
    if args.code_command == "status":
        from .runtime.repo_analyzer import RepoProfilesStore

        repo = RepoProfilesStore(config).get_latest() or RepoProfilesStore(config).scan()
        tests = agent.tests.list_runs(limit=5)
        console.print(json.dumps({"repo": repo.as_api(), "recent_tests": [test.as_api() for test in tests]}, ensure_ascii=False, indent=2))
        return 0
    if args.code_command == "patch-plan":
        from .runtime.patch_planner import PatchPlanner

        changes = []
        if args.file and args.content:
            changes.append({"relative_path": args.file, "content": args.content})
        plan = PatchPlanner(config).create_patch_plan(args.problem or "Patch plan manuel", agent.scan(), proposed_changes=changes)
        console.print(json.dumps(plan.as_api(), ensure_ascii=False, indent=2))
        return 0
    if args.code_command == "commit":
        from .runtime.tool_broker import ToolBroker

        if not config.code_allow_git_commit or not config.allow_git_write_in_workspace:
            console.print("[red]Git commit refuse par configuration.[/red]")
            return 1
        broker = ToolBroker(config)
        if not args.no_add_all:
            add_result = broker.call("git_add", {"relative_path": "."})
            if add_result.status != "completed":
                console.print(f"[red]{add_result.output}[/red]")
                return 1
        commit = broker.call("git_commit", {"message": args.message})
        if commit.status != "completed":
            console.print(f"[red]{commit.output}[/red]")
            return 1
        console.print(commit.output, markup=False)
        return 0
    if args.code_command == "doctor":
        from .runtime.repo_analyzer import RepoProfilesStore
        from .runtime.self_healing import SelfHealingEngine

        repo = RepoProfilesStore(config).get_latest() or RepoProfilesStore(config).scan()
        doctor = {
            "code_enabled": config.code_enabled,
            "workspace": str(config.workspace),
            "workspace_exists": config.workspace.exists(),
            "repo_detected": repo.is_git_repo,
            "test_commands": repo.test_commands,
            "git_commit_allowed": config.code_allow_git_commit and config.allow_git_write_in_workspace,
            "git_push_allowed": config.code_allow_git_push,
            "self_healing": SelfHealingEngine(config).status(),
        }
        console.print(json.dumps(doctor, ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega code scan|test|diff|status|patch-plan|commit|doctor")
    return 2


def self_healing_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.self_healing import SelfHealingEngine

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    engine = SelfHealingEngine(config)
    if args.self_healing_command == "status":
        console.print(json.dumps(engine.status(), ensure_ascii=False, indent=2))
        return 0
    if args.self_healing_command == "test":
        classified = engine.classify_error(args.error, {})
        suggestion = engine.suggest_recovery(classified.error_type, {})
        console.print(json.dumps({"classified_error": classified.as_api(), "suggestion": suggestion.as_api()}, ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega self-healing status|test [error]")
    return 2


def memory_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.project_memory import ProjectMemoryStore, default_project_memory_provenance

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    store = ProjectMemoryStore(config)
    if args.memory_command == "list":
        try:
            memories = store.list_memories(scope=args.scope, project_id=args.project, status=args.status)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        for memory in memories:
            console.print(f"{memory.id} [{memory.scope}/{memory.type}] p{memory.importance} c{memory.confidence:.2f} {memory.key}: {memory.content}", markup=False)
        return 0
    if args.memory_command == "search":
        try:
            memories = store.search_memory(args.query, scope=args.scope, project_id=args.project)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        for memory in memories:
            console.print(f"{memory.id} [{memory.scope}/{memory.type}] {memory.key}: {memory.content}", markup=False)
        return 0
    if args.memory_command == "add":
        try:
            memory = store.create_memory(
                scope=args.scope,
                project_id=args.project,
                scope_id=args.project if args.scope == "project" else None,
                content=args.content,
                type=args.type,
                key=args.key,
                tags=[tag.strip() for tag in args.tags.split(",") if tag.strip()],
                provenance=default_project_memory_provenance("CLI"),
            )
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Memoire ajoutee: {memory.id}")
        return 0
    if args.memory_command == "delete":
        if not store.delete_memory(args.memory_id):
            console.print("[red]Memoire introuvable.[/red]")
            return 1
        console.print("Memoire supprimee.")
        return 0
    if args.memory_command == "suggestions":
        for suggestion in store.list_suggestions():
            console.print(f"{suggestion.id} [{suggestion.suggested_type}] run={suggestion.run_id}: {suggestion.content}", markup=False)
        return 0
    if args.memory_command == "accept":
        try:
            memory = store.accept_suggestion(args.suggestion_id)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        if memory is None:
            console.print("[red]Suggestion introuvable.[/red]")
            return 1
        console.print(f"Suggestion acceptee: {memory.id}")
        return 0
    if args.memory_command == "reject":
        if not store.reject_suggestion(args.suggestion_id):
            console.print("[red]Suggestion introuvable.[/red]")
            return 1
        console.print("Suggestion rejetee.")
        return 0
    if args.memory_command == "compact":
        console.print(json.dumps(store.compact_project_memory(args.project), ensure_ascii=False, indent=2))
        return 0
    console.print("Commandes: omega memory list|search|add|delete|suggestions|accept|reject|compact")
    return 2


def decisions_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .runtime.decision_log import DecisionLog
    from .runtime.project_memory import default_project_memory_provenance

    _load_legacy_dotenv_if_needed()
    config = OmegaConfig.from_env()
    decisions = DecisionLog(config)
    if args.decisions_command == "list":
        for decision in decisions.list_decisions(project_id=args.project):
            console.print(f"{decision.id} [{decision.status}] {decision.created_at} - {decision.title}: {decision.content}", markup=False)
        return 0
    if args.decisions_command == "add":
        try:
            decision = decisions.add_decision(
                args.title,
                args.content,
                args.reason,
                project_id=args.project,
                provenance=default_project_memory_provenance("CLI"),
            )
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"Decision ajoutee: {decision.id}")
        return 0
    if args.decisions_command == "archive":
        if decisions.archive_decision(args.decision_id) is None:
            console.print("[red]Decision introuvable.[/red]")
            return 1
        console.print("Decision archivee.")
        return 0
    console.print("Commandes: omega decisions list|add|archive")
    return 2



def config_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig, VALID_PROVIDERS
    from .config_store import (
        config_path,
        ensure_default_config,
        get_config_value,
        migrate_env_to_config,
        parse_cli_value,
        redact_config_for_display,
        set_config_value,
        unset_config_value,
    )

    _load_legacy_dotenv_if_needed()
    if args.config_command == "path":
        console.print(str(config_path()))
        return 0
    if args.config_command == "init":
        target = config_path()
        if target.exists() and not args.force:
            console.print(f"Config deja presente: {target}")
            return 0
        ensure_default_config(target)
        console.print(f"Config creee: {target}")
        return 0
    if args.config_command == "show":
        console.print(json.dumps(redact_config_for_display(), ensure_ascii=False, indent=2))
        return 0
    if args.config_command == "show-raw":
        console.print(json.dumps(redact_config_for_display(), ensure_ascii=False, indent=2))
        return 0
    if args.config_command == "get":
        value = get_config_value(args.path)
        console.print(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
        return 0
    if args.config_command == "set":
        set_config_value(args.path, parse_cli_value(args.value))
        console.print(f"{args.path} = {args.value}")
        return 0
    if args.config_command == "unset":
        unset_config_value(args.path)
        console.print(f"{args.path} supprime")
        return 0
    if args.config_command == "migrate-env":
        result = migrate_env_to_config(force=args.force)
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("legacy_env_present"):
            console.print(".env est legacy. La nouvelle source de verite est config.json.")
        return 0
    if args.config_command == "doctor":
        config = OmegaConfig.from_env()
        failed = False
        checks = [
            ("Config path", bool(config.config_path), str(config.config_path)),
            ("Config status", config.config_status == "OK", config.config_status),
            ("Default model", bool(config.default_model_ref), config.default_model_ref),
            ("Provider actif", config.provider in VALID_PROVIDERS, config.provider),
            ("Workspace", config.workspace.exists(), str(config.workspace)),
        ]
        for name, ok, detail in checks:
            console.print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
            failed = failed or not ok
        return 1 if failed else 0
    console.print("Commandes: omega config path|init|show|get <path>|set <path> <value>|unset <path>|migrate-env|doctor")
    return 2


def secrets_command(args: argparse.Namespace) -> int:
    from .config_store import expected_secret_status

    if args.secrets_command == "status":
        for item in expected_secret_status():
            console.print(f"{item['name']}: configured={str(item['configured']).lower()}")
        return 0
    if args.secrets_command == "set-env":
        _set_user_environment_variable(args.name, args.value)
        console.print(f"{args.name}: configured=true")
        console.print("Rouvre PowerShell pour que la variable soit visible dans les nouveaux processus.")
        return 0
    console.print("Commandes: omega secrets status|set-env <NAME> <VALUE>")
    return 2


def _set_provider_config_enabled(provider: str, enabled: bool) -> None:
    from .config import VALID_PROVIDERS
    from .config_store import save_config, set_config_value

    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Provider inconnu: {provider}")
    data = set_config_value(f"providers.{provider}.enabled", enabled)
    save_config(data)


def _set_provider_base_url(provider: str, url: str) -> None:
    from .config import VALID_PROVIDERS
    from .config_store import save_config, set_config_value

    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Provider inconnu: {provider}")
    data = set_config_value(f"providers.{provider}.base_url", url)
    save_config(data)


def _set_user_environment_variable(name: str, value: str) -> None:
    if not name or any(char in name for char in " =\t\r\n"):
        raise ValueError("Nom de variable invalide.")
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::SetEnvironmentVariable($args[0], $args[1], 'User')",
                name,
                value,
            ],
            check=True,
        )
    else:
        console.print("[yellow]Set-env persistant est implemente pour Windows. Variable exportee pour ce processus seulement.[/yellow]")
        os.environ[name] = value


def security_command(args: argparse.Namespace) -> int:
    from .config import OmegaConfig
    from .security.audit import apply_safe_fixes, run_security_audit

    _load_legacy_dotenv_if_needed()
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
    raise SystemExit(main())
