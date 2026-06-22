from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import urlsplit, urlunsplit


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateOptions:
    force: bool = False
    branch: str | None = None
    skip_frontend: bool = False
    skip_doctor: bool = False


@dataclass(frozen=True)
class InstallationState:
    root: Path
    version: str
    commit: str
    branch: str
    origin: str
    upstream: str | None
    dirty_files: tuple[str, ...]
    venv_exists: bool
    frontend_exists: bool
    package_json_exists: bool
    config_exists: bool


@dataclass
class UpdateSummary:
    old_commit: str = ""
    new_commit: str = ""
    branch: str = ""
    origin: str = ""
    config_backup: str | None = None
    policy_backups: list[str] = field(default_factory=list)
    stash_ref: str | None = None
    python_updated: bool = False
    frontend_status: str = "not-run"
    doctors_status: str = "skipped"

    @property
    def succeeded(self) -> bool:
        return self.python_updated and self.doctors_status != "fail"


class OmegaUpdater:
    def __init__(
        self,
        install_dir: Path | str | None = None,
        config_file: Path | str | None = None,
        emit: Callable[[str], None] | None = None,
    ):
        self.install_dir = Path(install_dir).expanduser().resolve() if install_dir else Path(__file__).resolve().parents[1]
        if config_file is None:
            from omega_agent.config_store import config_path

            self.config_file = config_path()
        else:
            self.config_file = Path(config_file).expanduser().resolve()
        self.emit = emit or print

    def inspect(self) -> InstallationState:
        git = shutil.which("git")
        if not git:
            raise UpdateError("Git est introuvable. Installe Git avant de lancer omega update.")
        if not (self.install_dir / ".git").exists():
            raise UpdateError(f"Le dossier d'installation n'est pas un depot Git: {self.install_dir}")
        inside = self._run([git, "rev-parse", "--is-inside-work-tree"], cwd=self.install_dir).stdout.strip()
        if inside.lower() != "true":
            raise UpdateError(f"Le dossier d'installation n'est pas un depot Git valide: {self.install_dir}")

        branch = self._git_output("branch", "--show-current")
        commit = self._git_output("rev-parse", "HEAD")
        origin = self._git_output("remote", "get-url", "origin")
        upstream_result = self._git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
        upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else None
        dirty = tuple(line for line in self._git_output("status", "--porcelain").splitlines() if line.strip())
        frontend = self.install_dir / "omega_control"
        return InstallationState(
            root=self.install_dir,
            version=_project_version(self.install_dir),
            commit=commit,
            branch=branch,
            origin=origin,
            upstream=upstream,
            dirty_files=dirty,
            venv_exists=(self.install_dir / ".venv").is_dir(),
            frontend_exists=frontend.is_dir(),
            package_json_exists=(frontend / "package.json").is_file(),
            config_exists=self.config_file.is_file(),
        )

    def update(self, options: UpdateOptions) -> UpdateSummary:
        state = self.inspect()
        self._print_installation_state(state)
        if not options.branch and state.branch != "main" and not state.upstream:
            branch = state.branch or "(detached HEAD)"
            raise UpdateError(
                f"Cette branche n'a pas d'upstream. Utilise git push -u origin {branch} "
                "ou lance omega update --branch main."
            )
        if not state.branch and not options.branch:
            raise UpdateError("HEAD est detache. Lance omega update --branch main ou indique une branche explicite.")
        if state.dirty_files and not options.force:
            files = "\n".join(f"  {line}" for line in state.dirty_files)
            raise UpdateError(
                "Le depot contient des modifications locales. Update refuse sans --force.\n"
                f"{files}\n"
                "Relance avec omega update --force pour les conserver dans un stash."
            )

        summary = UpdateSummary(
            old_commit=state.commit,
            new_commit=state.commit,
            branch=state.branch,
            origin=state.origin,
        )
        summary.config_backup, summary.policy_backups = self.backup_user_files()
        if state.dirty_files:
            summary.stash_ref = self._stash_local_changes()

        self._update_git(options, state)
        summary.new_commit = self._git_output("rev-parse", "HEAD")
        summary.branch = self._git_output("branch", "--show-current")

        venv_python = self._update_python()
        summary.python_updated = True
        summary.frontend_status = self._update_frontend(skip=options.skip_frontend)
        self._merge_config_after_update(venv_python)
        summary.doctors_status = self._run_doctors(venv_python, skip=options.skip_doctor)
        return summary

    def backup_user_files(self) -> tuple[str | None, list[str]]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        config_backup: str | None = None
        if self.config_file.exists():
            backup = _available_backup_path(
                self.config_file.with_name(f"config.backup.{timestamp}.json")
            )
            try:
                shutil.copy2(self.config_file, backup)
            except OSError as exc:
                raise UpdateError(
                    f"Backup config impossible ({self.config_file} -> {backup}): {exc}"
                ) from exc
            config_backup = str(backup)
            self.emit(f"Backup config: {backup}")

        policy_backups: list[str] = []
        for name in ("policy.json", "policies.json", "policy_rules.json"):
            source = self.config_file.parent / name
            if not source.is_file():
                continue
            backup = _available_backup_path(
                source.with_name(f"{source.stem}.backup.{timestamp}{source.suffix}")
            )
            try:
                shutil.copy2(source, backup)
            except OSError as exc:
                raise UpdateError(
                    f"Backup policy impossible ({source} -> {backup}): {exc}"
                ) from exc
            policy_backups.append(str(backup))
            self.emit(f"Backup policy: {backup}")
        return config_backup, policy_backups

    def _print_installation_state(self, state: InstallationState) -> None:
        self.emit(f"Installation: {state.root}")
        self.emit(f"Version actuelle: {state.version or 'inconnue'}")
        self.emit(f"Commit actuel: {_short_commit(state.commit)}")
        self.emit(f"Branche: {state.branch or '(detached HEAD)'}")
        self.emit(f"Origin: {_redact_remote(state.origin)}")
        self.emit(f"Working tree: {'dirty' if state.dirty_files else 'clean'}")
        self.emit(f"Venv: {'present' if state.venv_exists else 'absent'}")
        self.emit(f"Omega Control: {'present' if state.frontend_exists else 'absent'}")
        self.emit(f"package.json: {'present' if state.package_json_exists else 'absent'}")
        self.emit(f"config.json: {'present' if state.config_exists else 'absent'}")

    def _stash_local_changes(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = f"Omega Agent update {timestamp}"
        self._git("stash", "push", "-u", "-m", message)
        stash_ref = self._git_output("stash", "list", "-1", "--format=%gd") or "stash@{0}"
        self.emit(f"Modifications locales conservees dans {stash_ref}: {message}")
        return stash_ref

    def _update_git(self, options: UpdateOptions, state: InstallationState) -> None:
        self.emit("Git: fetch origin")
        self._git("fetch", "origin")
        if options.branch:
            self._checkout_branch(options.branch)
            self.emit(f"Git: pull --ff-only origin {options.branch}")
            self._git("pull", "--ff-only", "origin", options.branch)
            return
        if state.branch == "main":
            self.emit("Git: pull --ff-only origin main")
            self._git("pull", "--ff-only", "origin", "main")
            return
        self.emit(f"Git: pull --ff-only depuis {state.upstream}")
        self._git("pull", "--ff-only")

    def _checkout_branch(self, branch: str) -> None:
        local = self._git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
        if local.returncode == 0:
            self._git("checkout", branch)
            return
        remote = self._git("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False)
        if remote.returncode != 0:
            raise UpdateError(f"Branche introuvable sur origin: {branch}")
        self._git("checkout", "--track", "-b", branch, f"origin/{branch}")

    def _update_python(self) -> Path:
        venv = self.install_dir / ".venv"
        venv_python = _venv_python(venv)
        if not venv_python.exists():
            self.emit(f"Python: creation de la venv {venv}")
            self._run([sys.executable, "-m", "venv", str(venv)], cwd=self.install_dir)
        if not venv_python.exists():
            raise UpdateError(f"Python de la venv introuvable apres creation: {venv_python}")
        self.emit("Python dependencies: mise a jour de pip")
        self._run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=self.install_dir)
        self.emit("Python dependencies: installation editable")
        self._run([str(venv_python), "-m", "pip", "install", "-e", str(self.install_dir)], cwd=self.install_dir)
        return venv_python

    def _update_frontend(self, *, skip: bool) -> str:
        if skip:
            self.emit("Frontend: ignore (--skip-frontend)")
            return "skipped"
        frontend = self.install_dir / "omega_control"
        package_json = frontend / "package.json"
        if not package_json.is_file():
            self.emit("Frontend non mis a jour : omega_control/package.json introuvable")
            return "not-present"
        npm = shutil.which("npm")
        if not npm:
            self.emit("Frontend non mis à jour : Node.js introuvable")
            return "node-missing"
        try:
            package = json.loads(package_json.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateError(f"Frontend non mis a jour : package.json invalide: {exc}") from exc
        self.emit("Frontend: npm install")
        self._run([npm, "install"], cwd=frontend)
        if "build" not in dict(package.get("scripts") or {}):
            self.emit("Frontend: aucun script build")
            return "dependencies-only"
        self.emit("Frontend: npm run build")
        self._run([npm, "run", "build"], cwd=frontend)
        return "yes"

    def _merge_config_after_update(self, venv_python: Path) -> None:
        self.emit("Configuration: merge des nouvelles cles sans ecraser les valeurs utilisateur")
        env = os.environ.copy()
        env["OMEGA_CONFIG_PATH"] = str(self.config_file)
        self._run(
            [str(venv_python), "-m", "omega_agent.updater", "--merge-config", str(self.config_file)],
            cwd=self.install_dir,
            env=env,
        )

    def _run_doctors(self, venv_python: Path, *, skip: bool) -> str:
        if skip:
            self.emit("Doctors: ignores (--skip-doctor)")
            return "skipped"
        env = os.environ.copy()
        env["OMEGA_CONFIG_PATH"] = str(self.config_file)
        results = []
        for command in (["doctor"], ["workspace", "doctor"]):
            label = "omega " + " ".join(command)
            self.emit(f"Health check: {label}")
            result = self._run(
                [str(venv_python), "-m", "omega_agent.main", *command],
                cwd=self.install_dir,
                env=env,
                check=False,
            )
            if result.stdout.strip():
                self.emit(result.stdout.rstrip())
            if result.stderr.strip():
                self.emit(result.stderr.rstrip())
            results.append(result.returncode == 0)
        return "pass" if all(results) else "fail"

    def _git_output(self, *args: str) -> str:
        return self._git(*args).stdout.strip()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        git = shutil.which("git")
        if not git:
            raise UpdateError("Git est introuvable.")
        return self._run([git, *args], cwd=self.install_dir, check=check)

    def _run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                list(command),
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            raise UpdateError(f"Commande impossible: {_command_shape(command)}: {exc}") from exc
        if check and result.returncode != 0:
            output = (result.stderr or result.stdout or "").strip()
            raise UpdateError(
                f"Commande echouee ({result.returncode}): {_command_shape(command)}"
                + (f"\n{output}" if output else "")
            )
        return result


def merge_config_defaults(path: Path | str) -> Path:
    from omega_agent.config_store import load_config, save_config

    target = Path(path).expanduser().resolve()
    merged = load_config(target)
    return save_config(merged, target)


def print_update_summary(summary: UpdateSummary, emit: Callable[[str], None] | None = None) -> None:
    output = emit or print
    output("")
    output("Resume de la mise a jour")
    output(f"  Ancien commit: {_short_commit(summary.old_commit)}")
    output(f"  Nouveau commit: {_short_commit(summary.new_commit)}")
    output(f"  Branche: {summary.branch or 'inconnue'}")
    output(f"  Config backup: {summary.config_backup or 'non necessaire'}")
    output(f"  Python dependencies updated: {'yes' if summary.python_updated else 'no'}")
    output(f"  Frontend updated: {summary.frontend_status}")
    output(f"  Doctors status: {summary.doctors_status}")
    if summary.stash_ref:
        output(f"  Modifications locales: conservees dans {summary.stash_ref}")


def _project_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return ""
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str((payload.get("project") or {}).get("version") or "")


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _short_commit(commit: str) -> str:
    return commit[:12] if commit else "inconnu"


def _command_shape(command: Sequence[str]) -> str:
    return " ".join(str(item) for item in command)


def _available_backup_path(preferred: Path) -> Path:
    if not preferred.exists():
        return preferred
    counter = 1
    while True:
        candidate = preferred.with_name(f"{preferred.stem}.{counter}{preferred.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _redact_remote(remote: str) -> str:
    if "://" not in remote:
        return remote
    parsed = urlsplit(remote)
    if "@" not in parsed.netloc:
        return remote
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit(
        (parsed.scheme, f"[REDACTED]@{hostname}", parsed.path, parsed.query, parsed.fragment)
    )


def _module_main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--merge-config")
    args = parser.parse_args(argv)
    if args.merge_config:
        merge_config_defaults(args.merge_config)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_module_main())
