from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

IGNORED_DIRS = {".git", ".omega", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}


@dataclass(frozen=True)
class RepoSummary:
    id: str | None
    project_id: str | None
    workspace_path: str
    is_git_repo: bool
    languages: list[str]
    frameworks: list[str]
    package_managers: list[str]
    test_commands: list[str]
    build_commands: list[str]
    entrypoints: list[str]
    config_files: list[str]
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict | None = None

    def as_api(self) -> dict:
        return redact(asdict(self))


def detect_repo_root(workspace: str | Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    if (root / ".git").exists():
        return root
    for child in root.iterdir() if root.exists() else []:
        if child.is_dir() and child.name not in IGNORED_DIRS and (child / ".git").exists():
            return child.resolve()
    return root


def detect_git_repo(workspace: str | Path) -> bool:
    return (detect_repo_root(workspace) / ".git").exists()


def detect_languages(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    languages: set[str] = set()
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "setup.py").exists():
        languages.add("python")
    if (root / "package.json").exists() or (root / "tsconfig.json").exists():
        languages.add("typescript" if _has_any(root, {".ts", ".tsx"}) else "javascript")
    if _has_any(root, {".py"}):
        languages.add("python")
    if _has_any(root, {".ts", ".tsx"}):
        languages.add("typescript")
    if _has_any(root, {".js", ".jsx"}):
        languages.add("javascript")
    if (root / "Dockerfile").exists():
        languages.add("docker")
    return sorted(languages)


def detect_frameworks(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    frameworks: set[str] = set()
    for manifest in _package_json_paths(root):
        package_json = _load_json(manifest)
        deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})} if isinstance(package_json, dict) else {}
        base = manifest.parent
        if "vite" in deps or (base / "vite.config.ts").exists() or (base / "vite.config.js").exists():
            frameworks.add("vite")
        if "next" in deps or (base / "next.config.js").exists() or (base / "next.config.ts").exists():
            frameworks.add("next")
        if "react" in deps:
            frameworks.add("react")
    if (root / "pytest.ini").exists() or (root / "tests").exists():
        frameworks.add("pytest")
    pyproject = _load_toml(root / "pyproject.toml")
    if _toml_mentions(pyproject, "pytest"):
        frameworks.add("pytest")
    if _toml_mentions(pyproject, "fastapi"):
        frameworks.add("fastapi")
    return sorted(frameworks)


def detect_package_managers(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    managers: list[str] = []
    for manifest in _package_json_paths(root):
        base = manifest.parent
        if (base / "package-lock.json").exists() and "npm" not in managers:
            managers.append("npm")
        if (base / "pnpm-lock.yaml").exists() and "pnpm" not in managers:
            managers.append("pnpm")
        if (base / "yarn.lock").exists() and "yarn" not in managers:
            managers.append("yarn")
        if "npm" not in managers and not any((base / lock).exists() for lock in ("pnpm-lock.yaml", "yarn.lock")):
            managers.append("npm")
    if (root / "pyproject.toml").exists():
        managers.append("pyproject")
    if (root / "requirements.txt").exists():
        managers.append("pip")
    return managers


def detect_test_commands(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    commands: list[str] = []
    for manifest in _package_json_paths(root):
        package_json = _load_json(manifest)
        scripts = package_json.get("scripts", {}) if isinstance(package_json, dict) else {}
        prefix = _npm_prefix(root, manifest.parent)
        if isinstance(scripts, dict):
            if "test" in scripts:
                commands.append(f"npm{prefix} test")
            if "test:unit" in scripts:
                commands.append(f"npm{prefix} run test:unit")
            if "build" in scripts:
                commands.append(f"npm{prefix} run build")
    if (root / "pytest.ini").exists() or (root / "tests").exists() or _toml_mentions(_load_toml(root / "pyproject.toml"), "pytest"):
        commands.append("pytest")
    return _dedupe(commands)


def detect_build_commands(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    commands: list[str] = []
    for manifest in _package_json_paths(root):
        package_json = _load_json(manifest)
        scripts = package_json.get("scripts", {}) if isinstance(package_json, dict) else {}
        if isinstance(scripts, dict) and "build" in scripts:
            commands.append(f"npm{_npm_prefix(root, manifest.parent)} run build")
    pyproject = _load_toml(root / "pyproject.toml")
    if pyproject:
        commands.append("python -m build")
    return _dedupe(commands)


def find_entrypoints(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    candidates = [
        "main.py",
        "app.py",
        "src/main.ts",
        "src/main.tsx",
        "src/App.tsx",
        "index.js",
        "server.js",
        "omega_agent/main.py",
    ]
    found = [item for item in candidates if (root / item).exists()]
    for manifest in _package_json_paths(root):
        if manifest.parent == root:
            continue
        for candidate in ("src/main.ts", "src/main.tsx", "src/App.tsx", "index.js", "server.js"):
            path = manifest.parent / candidate
            if path.exists():
                found.append(str(path.relative_to(root)).replace("\\", "/"))
    return _dedupe(found)


def find_config_files(workspace: str | Path) -> list[str]:
    root = detect_repo_root(workspace)
    candidates = [
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "pytest.ini",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "vite.config.ts",
        "next.config.js",
        "tsconfig.json",
        "Dockerfile",
        "docker-compose.yml",
        "README.md",
    ]
    found = [item for item in candidates if (root / item).exists()]
    for manifest in _package_json_paths(root):
        if manifest.parent == root:
            continue
        for candidate in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "vite.config.ts", "vite.config.js", "next.config.js", "tsconfig.json"):
            path = manifest.parent / candidate
            if path.exists():
                found.append(str(path.relative_to(root)).replace("\\", "/"))
    workflows = root / ".github" / "workflows"
    if workflows.exists():
        found.extend(str(path.relative_to(root)).replace("\\", "/") for path in workflows.glob("*") if path.is_file())
    return found


def summarize_repo(workspace: str | Path) -> RepoSummary:
    root = detect_repo_root(workspace)
    return RepoSummary(
        id=None,
        project_id=None,
        workspace_path=str(root),
        is_git_repo=(root / ".git").exists(),
        languages=detect_languages(root),
        frameworks=detect_frameworks(root),
        package_managers=detect_package_managers(root),
        test_commands=detect_test_commands(root),
        build_commands=detect_build_commands(root),
        entrypoints=find_entrypoints(root),
        config_files=find_config_files(root),
        metadata={"root_name": root.name},
    )


class RepoProfilesStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)
        with connect_runtime_db(config):
            pass

    def scan(self, project_id: str | None = None) -> RepoSummary:
        self.events.add("repo.scan.started", {"project_id": project_id})
        summary = summarize_repo(self.config.workspace)
        now = _now()
        profile_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO repo_profiles(
                    id, project_id, workspace_path, is_git_repo, languages_json, frameworks_json,
                    package_managers_json, test_commands_json, build_commands_json, entrypoints_json,
                    config_files_json, created_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    project_id,
                    summary.workspace_path,
                    int(summary.is_git_repo),
                    json.dumps(summary.languages, ensure_ascii=False),
                    json.dumps(summary.frameworks, ensure_ascii=False),
                    json.dumps(summary.package_managers, ensure_ascii=False),
                    json.dumps(summary.test_commands, ensure_ascii=False),
                    json.dumps(summary.build_commands, ensure_ascii=False),
                    json.dumps(summary.entrypoints, ensure_ascii=False),
                    json.dumps(summary.config_files, ensure_ascii=False),
                    now,
                    now,
                    json.dumps(summary.metadata or {}, ensure_ascii=False),
                ),
            )
        stored = self.get_latest(project_id=project_id) or summary
        self.events.add("repo.scan.completed", {"project_id": project_id, "repo_profile_id": getattr(stored, "id", None), "languages": summary.languages})
        return stored

    def get_latest(self, project_id: str | None = None) -> RepoSummary | None:
        sql = "SELECT * FROM repo_profiles"
        params: list[object] = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY updated_at DESC LIMIT 1"
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return _from_row(row) if row else None


def _from_row(row) -> RepoSummary:
    return RepoSummary(
        id=row["id"],
        project_id=row["project_id"],
        workspace_path=row["workspace_path"],
        is_git_repo=bool(row["is_git_repo"]),
        languages=_json_list(row["languages_json"]),
        frameworks=_json_list(row["frameworks_json"]),
        package_managers=_json_list(row["package_managers_json"]),
        test_commands=_json_list(row["test_commands_json"]),
        build_commands=_json_list(row["build_commands_json"]),
        entrypoints=_json_list(row["entrypoints_json"]),
        config_files=_json_list(row["config_files_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_json_dict(row["metadata_json"]),
    )


def _has_any(root: Path, suffixes: set[str]) -> bool:
    for path in _walk_files(root, max_files=500):
        if path.suffix.lower() in suffixes:
            return True
    return False


def _walk_files(root: Path, max_files: int = 1000):
    count = 0
    for path in root.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path
            count += 1
            if count >= max_files:
                return


def _package_json_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    root_manifest = root / "package.json"
    if root_manifest.exists():
        paths.append(root_manifest)
    if root.exists():
        for child in root.iterdir():
            if child.is_dir() and child.name not in IGNORED_DIRS:
                manifest = child / "package.json"
                if manifest.exists():
                    paths.append(manifest)
    return paths


def _npm_prefix(root: Path, package_dir: Path) -> str:
    if package_dir == root:
        return ""
    relative = str(package_dir.relative_to(root)).replace("\\", "/")
    return f" --prefix {_quote_command_arg(relative)}"


def _quote_command_arg(value: str) -> str:
    if not value:
        return value
    if any(char.isspace() for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _toml_mentions(value: object, needle: str) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower() if value else ""
    return needle.lower() in text


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
