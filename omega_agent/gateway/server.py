from __future__ import annotations

import importlib.metadata
import json
import socket
import subprocess
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from omega_agent.channels.registry import ChannelsRegistry
from omega_agent.codex_backend import codex_login_status_cached
from omega_agent.config import OmegaConfig
from omega_agent.gateway.routes import CODEX_DISCONNECTED_MESSAGE, create_router
from omega_agent.gateway.model_routes import create_model_router
from omega_agent.gateway.ws import create_ws_router
from omega_agent.runtime import OmegaRuntime
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.jobs import JobsStore
from omega_agent.runtime.memory import MemoryStore
from omega_agent.runtime.delegation import DelegationsStore
from omega_agent.runtime.multi_agent import MultiAgentRuntime
from omega_agent.runtime.model_selector import ModelSelector
from omega_agent.runtime.plugins_registry import PluginsRegistry
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.performance import PerformanceStore
from omega_agent.runtime.reasoning import ReasoningStore
from omega_agent.runtime.scheduler import ScheduledTasksStore, SchedulerLoop
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.settings import SettingsStore
from omega_agent.runtime.skills_registry import SkillsRegistry
from omega_agent.runtime.standing_orders import StandingOrdersStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tools_registry import list_tools

STATIC_DIR = Path(__file__).with_name("static")
CONTROL_DIST = Path(__file__).resolve().parents[2] / "omega_control" / "dist"


def codex_login_status():
    return codex_login_status_cached(300)


@dataclass(frozen=True)
class PortOwner:
    pid: int
    command: str = ""


class RuntimeState:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.version = _package_version()
        self.started_at = datetime.now(timezone.utc)
        with connect_runtime_db(config):
            pass
        self.codex_login_status = self._codex_login_status
        self.agent_profiles = AgentProfilesStore(config)
        self.channels = ChannelsRegistry(config)
        self.sessions = SessionsStore(config)
        self.projects = ProjectsStore(config)
        self.approvals = ApprovalsStore(config)
        self.events = EventsStore(config)
        self.reasoning = ReasoningStore(config)
        self.jobs = JobsStore(config)
        self.scheduled_tasks = ScheduledTasksStore(config)
        self.scheduler_loop = SchedulerLoop(config)
        self.standing_orders = StandingOrdersStore(config)
        self.memory = MemoryStore(config)
        self.delegations = DelegationsStore(config)
        self.multi_agent = MultiAgentRuntime(config)
        self.settings = SettingsStore(config)
        self.model_selector = ModelSelector(config)
        self.skills = SkillsRegistry(config)
        self.plugins = PluginsRegistry(config)
        self.performance = PerformanceStore(config)
        self._status_cache: tuple[float, dict] | None = None
        self._tools_cache = []
        self._skills_cache = []
        self._plugins_cache = []
        self.reload_registries(log_event=False)
        if config.provider == "codex":
            codex_login_status_cached(config.codex_auth_cache_seconds, force=True)
        self._runtime: OmegaRuntime | None = None
        self._lock = Lock()

    def _codex_login_status(self, force: bool = False):
        if force:
            return codex_login_status_cached(self.config.codex_auth_cache_seconds, force=True)
        return codex_login_status()

    def tools(self):
        return list(self._tools_cache)

    def skills_list(self):
        return list(self._skills_cache)

    def plugins_list(self):
        return list(self._plugins_cache)

    def reload_registries(self, log_event: bool = True):
        self._tools_cache = list_tools(self.config)
        self._skills_cache = self.skills.list()
        self._plugins_cache = self.plugins.list()
        self._status_cache = None
        if log_event:
            self.events.add("registries.reloaded", {"tools": len(self._tools_cache), "skills": len(self._skills_cache), "plugins": len(self._plugins_cache)})
        return {"tools": len(self._tools_cache), "skills": len(self._skills_cache), "plugins": len(self._plugins_cache)}

    def cached_status(self, builder):
        import time

        now = time.monotonic()
        if self._status_cache is not None:
            expires_at, payload = self._status_cache
            if now < expires_at:
                return payload
        payload = builder()
        self._status_cache = (now + self.config.status_cache_seconds, payload)
        return payload

    def runtime(self) -> OmegaRuntime:
        with self._lock:
            if self._runtime is None:
                try:
                    self._runtime = OmegaRuntime(
                        self.config,
                        tools_provider=self.tools,
                        skills_provider=self.skills_list,
                        performance_store=self.performance,
                        model_selector=self.model_selector,
                    )
                except TypeError:
                    self._runtime = OmegaRuntime(self.config)
            return self._runtime


def create_app(config: OmegaConfig | None = None) -> FastAPI:
    cfg = config or OmegaConfig.from_env()
    app = FastAPI(title="Omega Gateway")
    app.state.gateway_state = RuntimeState(cfg)
    app.include_router(create_router())
    app.include_router(create_model_router())
    app.include_router(create_ws_router())

    if CONTROL_DIST.exists():
        assets = CONTROL_DIST / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        index_file = CONTROL_DIST / "index.html"
    else:
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
        index_file = STATIC_DIR / "index.html"

    @app.get("/")
    async def index():
        return FileResponse(index_file)

    @app.on_event("startup")
    async def _start_scheduler():
        app.state.gateway_state.scheduler_loop.start()

    @app.on_event("shutdown")
    async def _stop_scheduler():
        await app.state.gateway_state.scheduler_loop.stop()

    return app


def serve_gateway(config: OmegaConfig, host: str, port: int, open_browser: bool, reuse_existing: bool = False) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Le port Omega Gateway doit être entre 1 et 65535.")
    config = replace(config, host=host, port=port, open_browser=open_browser)
    url = f"http://{host}:{port}"
    if is_gateway_running(host, port):
        if reuse_existing:
            print(f"Omega Gateway est déjà lancé sur {url}")
            if open_browser:
                webbrowser.open(url)
            return
        raise RuntimeError(f"Omega Gateway est déjà lancé sur {url}")
    owner = find_port_owner(port)
    if owner is not None:
        command = f" ({owner.command})" if owner.command else ""
        raise RuntimeError(
            f"Le port {port} est déjà utilisé par un autre processus: PID {owner.pid}{command}.\n"
            f"PowerShell: Stop-Process -Id {owner.pid} -Force"
        )
    print(f"Omega Gateway running at {url}")
    if open_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(config), host=host, port=port)


def is_gateway_running(host: str, port: int, timeout: float = 0.8) -> bool:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    try:
        with urllib.request.urlopen(f"http://{probe_host}:{port}/health", timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return bool(payload.get("ok")) and "version" in payload
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def find_port_owner(port: int) -> PortOwner | None:
    if not _is_port_open(port):
        return None
    return _find_port_owner_powershell(port) or _find_port_owner_netstat(port)


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _find_port_owner_powershell(port: int) -> PortOwner | None:
    script = (
        f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($c) { "
        "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{ pid=$c.OwningProcess; command=if($p){$p.CommandLine}else{''} } | ConvertTo-Json -Compress "
        "}"
    )
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
        return PortOwner(pid=int(payload["pid"]), command=str(payload.get("command") or ""))
    except (TypeError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _find_port_owner_netstat(port: int) -> PortOwner | None:
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    needle = f":{int(port)}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper().startswith("TCP") and needle in parts[1] and parts[3].upper() == "LISTENING":
            try:
                return PortOwner(pid=int(parts[-1]), command="")
            except ValueError:
                return None
    return None


def _package_version() -> str:
    try:
        return importlib.metadata.version("omega-agent")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"
