from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.error_taxonomy import classify_error
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.repo_analyzer import detect_test_commands
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.policy import parse_command
from omega_agent.security.redaction import redact, redact_text


@dataclass(frozen=True)
class TestRunResult:
    id: str
    run_id: str | None
    project_id: str | None
    command: str
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    summary: str
    started_at: str
    completed_at: str | None
    metadata: dict
    metadata_json: str

    def as_api(self) -> dict:
        return redact(asdict(self))


def run_detected_tests(workspace: str | Path, config: OmegaConfig | None = None) -> TestRunResult:
    commands = detect_test_commands(workspace)
    if not commands:
        now = _now()
        return TestRunResult(uuid4().hex, None, None, "", "error", None, "", "", "Aucune commande de test detectee.", now, now, {}, "{}")
    return run_command(_choose_test_command(commands), workspace, config=config)


def run_command(command: str, workspace: str | Path, config: OmegaConfig | None = None) -> TestRunResult:
    started_at = _now()
    workspace_path = Path(workspace).expanduser().resolve()
    if not workspace_path.exists() or not workspace_path.is_dir():
        completed_at = _now()
        return _result(command, "error", None, "", "", "Workspace introuvable.", started_at, completed_at, {})
    try:
        args = _validate_test_command(command, config)
    except Exception as exc:
        completed_at = _now()
        return _result(command, "error", None, "", "", f"Commande refusee: {exc}", started_at, completed_at, {"error_type": "permission_denied"})
    try:
        completed = subprocess.run(
            args,
            cwd=workspace_path,
            env=_test_env(config, workspace_path),
            capture_output=True,
            text=True,
            timeout=max(1, min(int(getattr(config, "code_test_timeout_seconds", 120) or 120), 900)),
            check=False,
        )
        max_chars = max(1000, int(getattr(config, "code_max_output_chars", 12000) or 12000))
        stdout = _limit(redact_text(completed.stdout or ""), max_chars)
        stderr = _limit(redact_text(completed.stderr or ""), max_chars // 2)
        combined = f"{stdout}\n{stderr}"
        status = "passed" if completed.returncode == 0 else "failed"
        summary = "Tests passes." if status == "passed" else summarize_test_failure(combined)
        metadata = {}
        if status != "passed":
            classified = classify_error(combined, {"command": command})
            metadata["classified_error"] = classified.as_api()
        return _result(command, status, completed.returncode, stdout, stderr, summary, started_at, _now(), metadata)
    except subprocess.TimeoutExpired as exc:
        stdout = _limit(redact_text(exc.stdout or ""), int(getattr(config, "code_max_output_chars", 12000) or 12000))
        stderr = _limit(redact_text(exc.stderr or ""), 4000)
        return _result(command, "error", None, stdout, stderr, "Commande interrompue: timeout.", started_at, _now(), {"error_type": "network_error"})
    except FileNotFoundError:
        return _result(command, "error", None, "", "", "Commande introuvable.", started_at, _now(), {"error_type": "command_not_found"})


def parse_pytest_output(output: str) -> dict:
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    failures = [line for line in lines if line.startswith("FAILED ") or "AssertionError" in line or line.startswith("ERROR ")]
    summary = next((line for line in reversed(lines) if " failed" in line or " passed" in line or " error" in line), "")
    return {"failures": failures[:20], "summary": summary}


def parse_npm_output(output: str) -> dict:
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    errors = [line for line in lines if "npm ERR!" in line or "error" in line.lower() or "failed" in line.lower()]
    return {"errors": errors[:20], "summary": errors[0] if errors else ""}


def summarize_test_failure(output: str) -> str:
    pytest_summary = parse_pytest_output(output)
    if pytest_summary["failures"]:
        return "; ".join(pytest_summary["failures"][:3])
    if pytest_summary["summary"]:
        return pytest_summary["summary"]
    npm_summary = parse_npm_output(output)
    if npm_summary["summary"]:
        return npm_summary["summary"]
    for line in str(output or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:500]
    return "Tests en echec sans sortie exploitable."


class CodeTestRunner:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def run_detected_tests(self, project_id: str | None = None, run_id: str | None = None) -> TestRunResult:
        commands = detect_test_commands(self.config.workspace)
        if not commands:
            result = _result("", "error", None, "", "", "Aucune commande de test detectee.", _now(), _now(), {})
            return self.store_test_run(result, project_id=project_id, run_id=run_id)
        return self.run_command(_choose_test_command(commands), project_id=project_id, run_id=run_id)

    def run_command(self, command: str, project_id: str | None = None, run_id: str | None = None) -> TestRunResult:
        self.events.add("test.run.started", {"command": command, "project_id": project_id, "run_id": run_id})
        result = run_command(command, self.config.workspace, config=self.config)
        stored = self.store_test_run(result, project_id=project_id, run_id=run_id)
        event_type = "test.run.completed" if stored.status == "passed" else "test.run.failed"
        self.events.add(event_type, {"test_run_id": stored.id, "command": command, "status": stored.status, "summary": stored.summary, "run_id": run_id})
        if stored.metadata.get("classified_error"):
            self.events.add("error.classified", stored.metadata["classified_error"])
        return stored

    def store_test_run(self, result: TestRunResult, project_id: str | None = None, run_id: str | None = None) -> TestRunResult:
        stored = TestRunResult(
            id=result.id,
            run_id=run_id or result.run_id,
            project_id=project_id or result.project_id,
            command=result.command,
            status=result.status,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            summary=result.summary,
            started_at=result.started_at,
            completed_at=result.completed_at,
            metadata=result.metadata,
            metadata_json=json.dumps(redact(result.metadata), ensure_ascii=False),
        )
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO test_runs(id, run_id, project_id, command, status, exit_code, stdout, stderr, summary, started_at, completed_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.run_id,
                    stored.project_id,
                    stored.command,
                    stored.status,
                    stored.exit_code,
                    stored.stdout,
                    stored.stderr,
                    stored.summary,
                    stored.started_at,
                    stored.completed_at,
                    stored.metadata_json,
                ),
            )
        return stored

    def list_runs(self, project_id: str | None = None, limit: int = 100) -> list[TestRunResult]:
        sql = "SELECT * FROM test_runs"
        params: list[object] = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_from_row(row) for row in rows]


def store_test_run(result: TestRunResult, config: OmegaConfig) -> TestRunResult:
    return CodeTestRunner(config).store_test_run(result)


def _validate_test_command(command: str, config: OmegaConfig | None = None) -> list[str]:
    args = parse_command(
        command,
        full_access=True,
        allow_git_write=False,
    )
    executable = Path(args[0]).name.lower()
    if executable == "npm":
        _validate_npm_test_args(args)
    if executable in {"python", "py"}:
        if len(args) >= 3 and args[1] == "-m" and args[2] in {"pytest", "unittest", "compileall", "build"}:
            return args
        raise PermissionError("python autorise uniquement via -m pytest/unittest/compileall/build.")
    if executable == "pip":
        raise PermissionError("pip install n'est pas une commande de test.")
    if executable == "git" and (len(args) < 2 or args[1] not in {"status", "diff", "log", "show"}):
        raise PermissionError("git write refuse dans le test runner.")
    return _normalize_test_args(args)


def _choose_test_command(commands: list[str]) -> str:
    for command in commands:
        lowered = command.lower()
        if "pytest" in lowered or "unittest" in lowered:
            return command
    for command in commands:
        lowered = command.lower()
        if lowered.endswith(" test") or " run test" in lowered:
            return command
    return commands[0]


def _normalize_test_args(args: list[str]) -> list[str]:
    executable = Path(args[0]).name.lower()
    if executable == "pytest":
        return [sys.executable, "-m", "pytest", *args[1:]]
    if executable in {"python", "py"} and len(args) >= 3 and args[1] == "-m" and args[2] in {"pytest", "unittest", "compileall", "build"}:
        return [sys.executable, *args[1:]]
    return args


def _validate_npm_test_args(args: list[str]) -> None:
    command_args = args[1:]
    if len(command_args) >= 2 and command_args[0] == "--prefix":
        command_args = command_args[2:]
    if not command_args:
        raise PermissionError("npm autorise uniquement test/run dans le test runner.")
    if command_args[0] == "test":
        return
    if command_args[0] == "run" and len(command_args) >= 2:
        script = command_args[1].lower()
        allowed_prefixes = ("test", "build", "lint", "typecheck", "check")
        if script.startswith(allowed_prefixes):
            return
    raise PermissionError("npm autorise uniquement les scripts test/build/lint/typecheck/check dans le test runner.")


def _test_env(config: OmegaConfig | None, workspace: Path) -> dict[str, str]:
    sandbox_home = workspace / ".omega" / "test-home"
    sandbox_home.mkdir(parents=True, exist_ok=True)
    env = {
        "HOME": str(sandbox_home),
        "USERPROFILE": str(sandbox_home),
        "OMEGA_WORKSPACE": str(workspace),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _result(command: str, status: str, exit_code: int | None, stdout: str, stderr: str, summary: str, started_at: str, completed_at: str, metadata: dict) -> TestRunResult:
    return TestRunResult(
        id=uuid4().hex,
        run_id=None,
        project_id=None,
        command=command,
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        summary=summary,
        started_at=started_at,
        completed_at=completed_at,
        metadata=redact(metadata),
        metadata_json=json.dumps(redact(metadata), ensure_ascii=False),
    )


def _from_row(row) -> TestRunResult:
    metadata_json = row["metadata_json"] or "{}"
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        metadata = {}
    return TestRunResult(
        id=row["id"],
        run_id=row["run_id"],
        project_id=row["project_id"],
        command=row["command"],
        status=row["status"],
        exit_code=row["exit_code"],
        stdout=row["stdout"],
        stderr=row["stderr"],
        summary=row["summary"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        metadata=metadata,
        metadata_json=metadata_json,
    )


def _limit(value: str, max_chars: int) -> str:
    text = value or ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
