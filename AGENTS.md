# AGENTS.md — Omega Agent rules for Codex

You are working on Omega Agent, a personal local AI agent.

Hard rules:
- Keep permissions minimal.
- Do not add global filesystem access.
- Do not add `sudo` or privileged execution.
- Do not read secrets by default.
- All tools must be scoped to `OMEGA_WORKSPACE` unless explicitly reviewed.
- Add or update tests for every security-sensitive change.
- Run `pytest` before finalizing changes.

Project priorities:
1. Safety
2. Predictability
3. Local developer UX
4. Extensibility

Gateway architecture:
- `omega` starts Omega Gateway and opens the local web UI.
- `omega serve` starts the FastAPI gateway only; `omega serve --no-open` is explicitly non-opening.
- `omega chat` keeps the legacy interactive CLI.
- Gateway code lives in `omega_agent/gateway/server.py`.
- REST routes live in `omega_agent/gateway/routes.py`.
- WebSocket routes live in `omega_agent/gateway/ws.py`.
- Pydantic API models live in `omega_agent/gateway/models.py`.
- Static UI assets live in `omega_agent/gateway/static/`.
- Omega Control React assets live in `omega_control/`.
- Shared chat behavior belongs in `omega_agent/runtime/agent.py`; do not duplicate agent logic in gateway routes.
- Sessions, approvals, events, tool registry, skill registry and plugin registry live under `omega_agent/runtime/`.
- Omega Reasoning Stream lives in `omega_agent/runtime/reasoning.py` and stores visible, redacted reasoning events only.
- Chat performance instrumentation lives in `omega_agent/runtime/performance.py`; keep request traces redacted and visible through `/api/performance/recent`.
- Provider/model selection lives in `omega_agent/providers/`, `omega_agent/runtime/model_selector.py`, and `omega_agent/gateway/model_routes.py`; never store API keys in SQLite or expose env values to the UI.
- Security policy lives in `omega_agent/security/policy.py`.
- Reasoning UI must never expose raw hidden chain-of-thought, provider-private thoughts, prompts, Codex credentials, secrets, SSH keys, browser cookies, or sensitive file contents.
- Default bind must remain `127.0.0.1:8765`.
- Any LAN/network bind must be explicit and must show a security warning.
- Gateway endpoints must not read Codex auth files directly; use Codex CLI status checks only.
- Plugins v0.1 are manifests only. Do not execute external plugin code.
