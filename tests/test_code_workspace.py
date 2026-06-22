import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.error_taxonomy import classify_error
from omega_agent.runtime.patch_planner import PatchPlanner
from omega_agent.runtime.repo_analyzer import (
    detect_git_repo,
    detect_languages,
    detect_package_managers,
    detect_test_commands,
    summarize_repo,
)
from omega_agent.runtime.self_healing import SelfHealingEngine
from omega_agent.runtime.test_runner import CodeTestRunner, parse_npm_output, parse_pytest_output, run_command
from omega_agent.runtime.tools_registry import HANDLERS
from omega_agent.tools.git import git_commit, git_diff, git_status


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "workspace_full_access": True,
        "shell_full_access_in_workspace": True,
        "allow_git_write_in_workspace": True,
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_repo_analyzer_detects_python_project(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts='-q'\n", encoding="utf-8")
    (workspace / "tests").mkdir()

    assert "python" in detect_languages(workspace)
    assert "pytest" in detect_test_commands(workspace)
    assert "pyproject" in detect_package_managers(workspace)


def test_repo_analyzer_detects_node_project(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text('{"scripts":{"test":"vitest","build":"vite build"},"dependencies":{"react":"latest","vite":"latest"}}', encoding="utf-8")
    (workspace / "package-lock.json").write_text("{}", encoding="utf-8")
    (workspace / "vite.config.ts").write_text("export default {}", encoding="utf-8")

    summary = summarize_repo(workspace)

    assert "npm" in summary.package_managers
    assert "vite" in summary.frameworks
    assert "npm test" in summary.test_commands
    assert "npm run build" in summary.build_commands


def test_repo_analyzer_detects_nested_node_project(tmp_path: Path):
    workspace = tmp_path / "workspace"
    app = workspace / "omega_control"
    app.mkdir(parents=True)
    (app / "package.json").write_text('{"scripts":{"build":"vite build"},"dependencies":{"react":"latest","vite":"latest"}}', encoding="utf-8")
    (app / "vite.config.ts").write_text("export default {}", encoding="utf-8")
    (app / "src").mkdir()
    (app / "src" / "App.tsx").write_text("export function App(){return null}\n", encoding="utf-8")

    summary = summarize_repo(workspace)

    assert "npm" in summary.package_managers
    assert "vite" in summary.frameworks
    assert "react" in summary.frameworks
    assert "npm --prefix omega_control run build" in summary.build_commands
    assert "omega_control/package.json" in summary.config_files
    assert "omega_control/src/App.tsx" in summary.entrypoints


def test_repo_analyzer_detects_git_and_empty_repo(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    assert summarize_repo(empty).languages == []
    assert detect_git_repo(repo) is True


def test_test_runner_executes_safe_command_and_limits_output(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    captured = {}

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        captured["args"] = args
        captured["cwd"] = cwd
        return SimpleNamespace(returncode=0, stdout="x" * 20000, stderr="")

    monkeypatch.setattr("omega_agent.runtime.test_runner.subprocess.run", fake_run)

    result = run_command("pytest", config.workspace, config=config)

    assert result.status == "passed"
    assert captured["cwd"] == config.workspace
    assert len(result.stdout) == config.code_max_output_chars
    assert captured["args"] == [sys.executable, "-m", "pytest"]

    npm_result = run_command("npm --prefix omega_control run build", config.workspace, config=config)
    assert npm_result.status == "passed"
    assert captured["args"] == ["npm", "--prefix", "omega_control", "run", "build"]

    (config.workspace / "tests").mkdir()
    app = config.workspace / "omega_control"
    app.mkdir()
    (app / "package.json").write_text('{"scripts":{"build":"vite build"}}', encoding="utf-8")
    CodeTestRunner(config).run_detected_tests()
    assert captured["args"] == [sys.executable, "-m", "pytest"]


def test_test_runner_parses_failures_and_stores_run(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="FAILED tests/test_app.py::test_x - AssertionError\n1 failed", stderr="")

    monkeypatch.setattr("omega_agent.runtime.test_runner.subprocess.run", fake_run)
    runner = CodeTestRunner(config)
    stored = runner.run_command("pytest")

    assert stored.status == "failed"
    assert "FAILED tests/test_app.py::test_x" in stored.summary
    assert runner.list_runs()[0].id == stored.id
    assert parse_pytest_output(stored.stdout)["failures"]
    assert parse_npm_output("npm ERR! missing script: test")["errors"]


def test_self_healing_classifies_and_suggests(tmp_path: Path):
    config = cfg(tmp_path)
    engine = SelfHealingEngine(config)

    assert classify_error("not a git repository").error_type == "git_not_repository"
    assert classify_error("JSONDecodeError: unexpected UTF-8 BOM").error_type == "json_decode_error"
    assert classify_error("EADDRINUSE port 8765").error_type == "port_in_use"
    suggestion = engine.suggest_recovery("git_not_repository", {"run_id": "r1"})

    assert "depot git" in suggestion.message
    assert engine.can_auto_recover("json_decode_error", {"run_id": "r1"}) is False


def test_patch_planner_creates_applies_and_diff(tmp_path: Path):
    config = cfg(tmp_path)
    planner = PatchPlanner(config)
    plan = planner.create_patch_plan(
        "Need file",
        summarize_repo(config.workspace),
        proposed_changes=[{"relative_path": "hello.py", "content": "print('ok')\n"}],
    )

    applied = planner.apply_patch_plan(plan.id)

    assert applied is not None
    assert applied.status == "applied"
    assert (config.workspace / "hello.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_git_tools_and_push_absent(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, allow_git_write_in_workspace=False)
    calls = []

    def fake_shell(config, command, *args, **kwargs):
        calls.append(command)
        return "ok"

    monkeypatch.setattr("omega_agent.tools.git._run_shell", fake_shell)

    assert git_status(config) == "ok"
    assert git_diff(config) == "ok"
    assert git_commit(config, "msg").startswith("Git commit refuse")
    assert "git_push" not in HANDLERS
    assert calls[:2] == ["git status", "git diff"]


def test_code_gateway_scan_tests_diff_and_events(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    (config.workspace / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (config.workspace / "tests").mkdir()

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr("omega_agent.runtime.test_runner.subprocess.run", fake_run)
    app = create_app(config)
    client = TestClient(app)

    scan = client.post("/api/code/scan", json={})
    test_run = client.post("/api/code/tests/run", json={})
    diff = client.get("/api/code/diff")
    events = client.get("/api/events").json()

    assert scan.status_code == 200
    assert "python" in scan.json()["languages"]
    assert test_run.status_code == 200
    assert test_run.json()["status"] == "passed"
    assert diff.status_code == 200
    assert any(event["type"] == "repo.scan.completed" for event in events)


def test_code_cli_test_routes_without_overwriting_top_level_command(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "OMEGA_CONFIG_PATH": str(tmp_path / "config.json"),
            "OMEGA_DB_PATH": str(tmp_path / "omega.db"),
            "OMEGA_WORKSPACE": str(workspace),
        }
    )

    completed = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "code", "test", "python -m compileall ."],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert '"command": "python -m compileall ."' in completed.stdout
    assert '"status": "passed"' in completed.stdout
