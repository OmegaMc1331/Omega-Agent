from __future__ import annotations

import os
import shutil
import subprocess
import time
from threading import Lock
from uuid import uuid4

from .config import OmegaConfig
from .security import log_action

CODEX_LOGIN_HINT = "Lance d'abord : codex login"
_AUTH_CACHE_LOCK = Lock()
_AUTH_CACHE: dict[str, object] = {"expires_at": 0.0, "value": None}


def codex_version() -> str | None:
    executable = shutil.which("codex")
    if not executable:
        return None
    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip()


def codex_login_status() -> tuple[bool, str]:
    executable = shutil.which("codex")
    if not executable:
        return False, "Codex CLI introuvable."
    result = subprocess.run(
        [executable, "login", "status"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0 and "logged in" in output.lower(), output


def clear_codex_auth_cache() -> None:
    with _AUTH_CACHE_LOCK:
        _AUTH_CACHE["expires_at"] = 0.0
        _AUTH_CACHE["value"] = None


def codex_login_status_cached(cache_seconds: int = 300, force: bool = False) -> tuple[bool, str]:
    now = time.monotonic()
    with _AUTH_CACHE_LOCK:
        cached = _AUTH_CACHE.get("value")
        if not force and cached is not None and now < float(_AUTH_CACHE.get("expires_at") or 0.0):
            return cached  # type: ignore[return-value]
    value = codex_login_status()
    with _AUTH_CACHE_LOCK:
        _AUTH_CACHE["value"] = value
        _AUTH_CACHE["expires_at"] = now + max(0, int(cache_seconds))
    return value


def ensure_codex_ready(config: OmegaConfig | None = None, *, force_auth_check: bool = False) -> str | None:
    if codex_version() is None:
        return "Codex CLI introuvable."
    if config is None or force_auth_check:
        is_logged_in, status = codex_login_status()
        with _AUTH_CACHE_LOCK:
            _AUTH_CACHE["value"] = (is_logged_in, status)
            _AUTH_CACHE["expires_at"] = time.monotonic() if not is_logged_in else time.monotonic() + 300
    else:
        is_logged_in, _ = codex_login_status_cached(config.codex_auth_cache_seconds)
    if not is_logged_in:
        return CODEX_LOGIN_HINT
    return None


def effective_codex_sandbox_mode(config: OmegaConfig) -> str:
    if config.workspace_full_access:
        return "workspace-write"
    return config.codex_sandbox_mode


def effective_codex_approval_policy(config: OmegaConfig) -> str:
    if config.workspace_full_access:
        return "never"
    return config.codex_approval_policy


def build_codex_prompt(history: list[dict[str, str]], user_input: str, config: OmegaConfig | None = None) -> str:
    recent_history = history[-12:]
    transcript = "\n".join(f"{item['role']}: {item['content']}" for item in recent_history)
    if config is not None and config.workspace_full_access:
        workspace_permissions = f"""
- Le Workspace Full Access Omega est actif pour {config.workspace}.
- Tu peux créer, modifier et supprimer des fichiers dans ce workspace quand la policy Omega l'autorise.
- Tu ne peux jamais écrire hors de ce workspace.
- Les actions restent soumises aux tools, aux limites de risque et aux policies Omega.
- Ne prétends pas être bloqué en lecture seule si une action workspace-safe est autorisée.
""".strip()
    else:
        workspace_permissions = """
- Respecte le sandbox et les approvals configurés par Omega.
- Tu ne peux jamais écrire hors du workspace Omega.
- Les actions restent soumises aux tools, aux limites de risque et aux policies Omega.
""".strip()
    return f"""
Tu es Omega Agent, l'agent IA personnel local-first d'Alexandre.

IDENTITÉ:
- Tu es Omega Agent, l'assistant IA personnel local-first d'Alexandre.
- Tu opères via Omega Gateway et Omega Control.
- Réponds en français par défaut.
- Le fournisseur de modèle est un détail technique interne. Ne le mentionne pas sauf si l'utilisateur demande explicitement le modèle, le provider ou la configuration technique.

CAPACITÉS:
- Tu peux aider à discuter, coder, analyser, planifier, documenter, explorer le workspace, utiliser les tools Omega, gérer des skills, des projets, des sessions et des tâches.
- Quand une action sensible est nécessaire, tu demandes une confirmation via le système d'approvals Omega.

SÉCURITÉ:
- Respecte le workspace sandboxé.
- Ne lis pas de secrets, clés SSH, tokens, mots de passe ou fichiers navigateur.
- Ne modifie pas de fichiers et n'exécute pas de commandes shell sans approval si la policy l'exige.
- Présente ces limites comme des règles Omega Agent, pas comme des limites d'un provider.
{workspace_permissions}

Historique récent:
{transcript}

Message utilisateur:
{user_input}
""".strip()


def run_codex_turn(config: OmegaConfig, history: list[dict[str, str]], user_input: str) -> str:
    try:
        ready_error = ensure_codex_ready(config)
    except TypeError:
        ready_error = ensure_codex_ready()
    if ready_error:
        return ready_error

    config.ensure_dirs()
    output_file = config.workspace / ".omega" / f"codex_last_message_{uuid4().hex}.txt"

    executable = shutil.which("codex")
    if not executable:
        return "Codex CLI introuvable."

    sandbox_mode = effective_codex_sandbox_mode(config)
    approval_policy = effective_codex_approval_policy(config)
    prompt = build_codex_prompt(history, user_input, config)
    command = [
        executable,
        "exec",
        "--model",
        config.model,
        "--cd",
        str(config.workspace),
        "--sandbox",
        sandbox_mode,
        "--ask-for-approval",
        approval_policy,
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--output-last-message",
        str(output_file),
        "-",
    ]
    env = os.environ.copy()
    env["OMEGA_WORKSPACE"] = str(config.workspace)

    result = subprocess.run(
        command,
        input=prompt,
        cwd=config.workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    log_action(
        config,
        "codex_exec",
        {
            "model": config.model,
            "returncode": result.returncode,
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
        },
    )

    if output_file.exists():
        output = output_file.read_text(encoding="utf-8", errors="replace").strip()
        if output:
            return output
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return output or f"Codex a échoué avec le code {result.returncode}."
    return output or "Codex n'a pas renvoyé de réponse."
