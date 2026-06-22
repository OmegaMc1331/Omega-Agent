from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from omega_agent.config import OmegaConfig
from omega_agent.config_store import save_config
from omega_agent.runtime.context import current_runtime_mode, runtime_context
from omega_agent.runtime.scheduler import SchedulerLoop
from omega_agent.runtime.storage import connect_runtime_db


def _cli_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    save_config(
        {
            "workspace": {
                "path": str(workspace),
                "full_access": True,
                "require_approval": False,
            },
            "paths": {
                "db_path": str(tmp_path / "omega.db"),
                "skills_dir": str(tmp_path / "skills"),
                "plugins_dir": str(tmp_path / "plugins"),
            },
            "evals": {"enabled": True},
            "shadow": {"enabled": True},
        },
        config_path,
    )
    return {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}, workspace


def test_cli_command_exits_fast(tmp_path: Path):
    env, _ = _cli_env(tmp_path)
    root = Path(__file__).resolve().parents[1]
    commands = [
        ["budgets", "profiles"],
        ["capabilities", "list"],
        ["code", "test", "python -m compileall ."],
        ["connectors", "list"],
        ["evals", "metrics"],
        ["policy", "simulate", "--tool", "write_file", "--path", "test.txt"],
        ["shadow", "create", "crée un fichier cli-shadow.txt avec OK"],
        ["skills", "candidates"],
        ["workflows", "templates"],
    ]

    for command in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "omega_agent.main", *command],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        assert completed.returncode in {0, 1}, completed.stdout + completed.stderr


def test_cli_does_not_start_gateway(tmp_path: Path):
    env, _ = _cli_env(tmp_path)
    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; "
        "from omega_agent.main import main; "
        "code = main(['config', 'path']); "
        "assert code == 0; "
        "assert 'omega_agent.gateway.server' not in sys.modules"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cli_does_not_start_scheduler(tmp_path: Path):
    config = OmegaConfig(
        model="test",
        workspace=tmp_path / "workspace",
        db_path=tmp_path / "omega.db",
        require_approval=False,
        scheduler_enabled=True,
    )

    with runtime_context("cli"):
        scheduler = SchedulerLoop(config)
        scheduler.start()

    assert scheduler._task is None


def test_cli_event_bus_no_background_threads(tmp_path: Path):
    from omega_agent.events.event_bus import EventBus

    config = OmegaConfig(
        model="test",
        workspace=tmp_path / "workspace",
        db_path=tmp_path / "omega.db",
        require_approval=False,
    )
    before = {
        thread.name
        for thread in threading.enumerate()
        if thread is not threading.main_thread() and thread.is_alive() and not thread.daemon
    }

    with runtime_context("cli"):
        EventBus(config).emit("cli.test", {"ok": True})

    after = {
        thread.name
        for thread in threading.enumerate()
        if thread is not threading.main_thread() and thread.is_alive() and not thread.daemon
    }
    assert after == before


def test_cli_commands_return_exit_code(monkeypatch):
    from omega_agent import main as main_module

    observed_modes: list[str] = []

    def fake_budgets_command(args):
        observed_modes.append(current_runtime_mode())
        return 0

    monkeypatch.setattr(main_module, "budgets_command", fake_budgets_command)

    assert main_module.main(["budgets", "profiles"]) == 0
    assert observed_modes == ["cli"]
    assert current_runtime_mode() == "server"


def test_connect_runtime_db_closes_connection(tmp_path: Path):
    config = OmegaConfig(
        model="test",
        workspace=tmp_path / "workspace",
        db_path=tmp_path / "omega.db",
        require_approval=False,
    )

    with connect_runtime_db(config) as conn:
        conn.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
