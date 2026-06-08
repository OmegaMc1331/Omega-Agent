from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace

from omega_agent.codex_backend import CODEX_LOGIN_HINT, run_codex_turn
from omega_agent.config import OmegaConfig
from omega_agent.providers.base import ProviderAuthError
from omega_agent.runtime.agent_profiles import DEFAULT_AGENT_PROFILE_ID, AgentProfile, AgentProfilesStore
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.model_selector import ModelSelector, split_model_ref
from omega_agent.runtime.performance import PerformanceStore
from omega_agent.runtime.project_context import use_project_config
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.reasoning import ReasoningSink, emit_reasoning_event_async
from omega_agent.runtime.router import choose_agent_profile
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.security.project_policy import project_config
from omega_agent.security.prompt_injection import scan_untrusted_content
from omega_agent.tools.files import copy_file, create_directory, delete_directory, delete_file, list_files, list_tree, move_file, read_file, write_file
from omega_agent.tools.memory import init_db, recall, remember
from omega_agent.tools.shell import run_shell

INSTRUCTIONS = """
Tu es Omega Agent, l'agent IA personnel local-first d'Alexandre.

Principes:
- Reponds en francais par defaut.
- Sois utile, direct et prudent.
- Utilise les outils seulement quand c'est necessaire.
- Tu n'as acces qu'au workspace configure.
- Avant une action risquee, explique brievement ce que tu vas faire.
- Ne tente jamais de contourner les limites de securite.
- Ne demande pas a lire des secrets, cles SSH, tokens ou mots de passe.
"""

try:
    from agents import Agent, Runner
except ModuleNotFoundError:
    Agent = None
    Runner = None


def build_agent(config: OmegaConfig, profile: AgentProfile | None = None):
    if Agent is None:
        raise RuntimeError("La dependance openai-agents n'est pas installee pour provider=openai. Lancez: pip install -e .")
    tool_by_id = {
        "list_files": list_files,
        "read_file": read_file,
        "write_file": write_file,
        "delete_file": delete_file,
        "create_directory": create_directory,
        "delete_directory": delete_directory,
        "move_file": move_file,
        "copy_file": copy_file,
        "list_tree": list_tree,
        "run_shell": run_shell,
        "remember": remember,
        "recall": recall,
        "search_memory": recall,
    }
    allowed = set(profile.allowed_tools) if profile and profile.allowed_tools else set(tool_by_id)
    return Agent(
        name=profile.name if profile else "Omega Agent",
        model=config.model,
        instructions=(profile.system_prompt if profile else INSTRUCTIONS) or INSTRUCTIONS,
        tools=[tool for tool_id, tool in tool_by_id.items() if tool_id in allowed],
    )


class OmegaRuntime:
    def __init__(
        self,
        config: OmegaConfig,
        *,
        tools_provider: Callable[[], list] | None = None,
        skills_provider: Callable[[], list] | None = None,
        performance_store: PerformanceStore | None = None,
        model_selector: ModelSelector | None = None,
    ):
        self.config = config
        init_db(config)
        self.sessions = SessionsStore(config)
        self.events = EventsStore(config)
        self.agent_profiles = AgentProfilesStore(config)
        self.projects = ProjectsStore(config)
        self.tools_provider = tools_provider
        self.skills_provider = skills_provider
        self.performance_store = performance_store
        self.model_selector = model_selector or ModelSelector(config)
        self.tool_broker = ToolBroker(config)

    async def send_message(
        self,
        message: str,
        session_id: str | None = None,
        channel_id: str | None = None,
        untrusted_input: bool = False,
        channel_type: str | None = None,
        reasoning_sink: ReasoningSink | None = None,
    ) -> str:
        perf = self.performance_store.start(session_id, {"provider": self.config.provider}) if self.performance_store else None
        session_id = session_id or self.sessions.default_session_id()
        if perf:
            perf.trace.session_id = session_id
        try:
            session = self.sessions.get_session(session_id)
            if session is None:
                raise ValueError("Session introuvable.")

            current_profile_id = session.active_agent_profile_id or DEFAULT_AGENT_PROFILE_ID
            selected_profile_id = choose_agent_profile(message, current_profile_id=current_profile_id)
            if selected_profile_id != current_profile_id:
                selected_profile = self.agent_profiles.get(selected_profile_id)
                if selected_profile is not None:
                    self.sessions.set_agent_profile(session_id, selected_profile_id)
                    self.events.add("agent.switched", {"from": current_profile_id, "to": selected_profile_id, "reason": "router"}, session_id=session_id)

            profile = self.agent_profiles.profile_for_session(session_id)
            history = self.sessions.list_messages(session_id)[-self.config.max_history_messages :]
            scan = scan_untrusted_content(message)
            if channel_id:
                self.sessions.merge_metadata(
                    session_id,
                    {
                        "channel_id": channel_id,
                        "channel_type": channel_type,
                        "external_channel": untrusted_input,
                        "untrusted_input": untrusted_input,
                    },
                )
            if perf:
                perf.mark("session_loaded")
                perf.annotate(history_items=len(history), reasoning_detail=self.config.reasoning_detail)

            metadata = {
                "untrusted": scan.untrusted or untrusted_input,
                "untrusted_input": untrusted_input,
                "channel_id": channel_id,
                "channel_type": channel_type,
                "prompt_injection_matches": scan.matches,
            }
            user_message = self.sessions.add_message(session_id, "user", message, metadata=metadata)
            if perf:
                perf.set_message_id(user_message.id)

            await emit_reasoning_event_async(
                session_id,
                "reasoning.started",
                "Omega reflechit",
                "J'analyse la demande avant d'agir.",
                config=self.config,
                status="running",
                metadata={"detail": self.config.reasoning_detail, "trace_id": perf.trace_id if perf else None},
                message_id=user_message.id,
                sink=reasoning_sink,
            )
            if perf:
                perf.mark("first_event_sent")

            await emit_reasoning_event_async(
                session_id,
                "reasoning.analysis",
                "Analyse de la demande",
                _short_analysis(message, scan.matches, untrusted_input),
                config=self.config,
                status="completed",
                metadata={"untrusted": scan.untrusted or untrusted_input, "matches": scan.matches},
                message_id=user_message.id,
                sink=reasoning_sink,
            )
            await emit_reasoning_event_async(
                session_id,
                "reasoning.plan",
                "Plan",
                _short_plan(message),
                config=self.config,
                status="completed",
                metadata={"probable_tools": _probable_tools(message)},
                message_id=user_message.id,
                sink=reasoning_sink,
            )
            self.events.add("message.created", {"session_id": session_id, "role": "user", "message_id": user_message.id}, session_id=session_id)
            if scan.untrusted:
                self.events.add("error", {"kind": "prompt_injection_warning", "warning": scan.warning, "matches": scan.matches}, session_id=session_id)
                await emit_reasoning_event_async(
                    session_id,
                    "reasoning.observation",
                    "Entree non fiable detectee",
                    scan.warning,
                    config=self.config,
                    status="completed",
                    metadata={"matches": scan.matches},
                    message_id=user_message.id,
                    sink=reasoning_sink,
                )

            project = self.projects.project_for_session(session_id)
            active_config = project_config(self.config, project.root_path, project.policy)
            resolved_model = self.model_selector.resolve_model(session_id=session_id, project_id=project.id, agent_profile_id=profile.id)
            provider_id, model_name = split_model_ref(resolved_model.primary_model_ref)
            active_config = replace(active_config, provider=provider_id, model=model_name)
            self.events.add("model.selected", resolved_model.as_api(), session_id=session_id)
            if perf:
                perf.annotate(model_ref=resolved_model.primary_model_ref, model_source=resolved_model.source_scope)

            await emit_reasoning_event_async(
                session_id,
                "reasoning.step",
                "Preparation du contexte",
                f"Session, projet et profil agent charges pour {project.name}.",
                config=self.config,
                status="completed",
                metadata={"project_id": project.id, "agent_profile_id": profile.id},
                message_id=user_message.id,
                sink=reasoning_sink,
            )

            identity_output = _identity_response_for_message(message, resolved_model.primary_model_ref)
            if identity_output is not None:
                output = identity_output
            else:
                direct_actions = _direct_actions_from_message(message)
                if direct_actions:
                    output = await self._execute_omega_actions(direct_actions, session_id, user_message.id, reasoning_sink)
                else:
                    try:
                        model_output = await self._run_model_turn(
                            active_config,
                            resolved_model.primary_model_ref,
                            session_id,
                            message,
                            history,
                            profile,
                            user_message.id,
                            reasoning_sink,
                            perf,
                        )
                    except Exception as primary_exc:
                        if not resolved_model.fallback_model_ref:
                            self.events.add("model.error", {"model_ref": resolved_model.primary_model_ref, "error": str(primary_exc)}, session_id=session_id)
                            raise
                        self.events.add("model.fallback", {"from": resolved_model.primary_model_ref, "to": resolved_model.fallback_model_ref, "error": str(primary_exc)}, session_id=session_id)
                        fallback_provider, fallback_model = split_model_ref(resolved_model.fallback_model_ref)
                        fallback_config = replace(active_config, provider=fallback_provider, model=fallback_model)
                        model_output = await self._run_model_turn(
                            fallback_config,
                            resolved_model.fallback_model_ref,
                            session_id,
                            message,
                            history,
                            profile,
                            user_message.id,
                            reasoning_sink,
                            perf,
                        )
                    actions = _extract_omega_actions(model_output)
                    if actions:
                        output = await self._execute_omega_actions(actions, session_id, user_message.id, reasoning_sink)
                    else:
                        output = model_output
        except Exception as exc:
            await emit_reasoning_event_async(
                session_id,
                "reasoning.error",
                "Erreur",
                str(exc),
                config=self.config,
                status="failed",
                message_id=perf.trace.message_id if perf else None,
                sink=reasoning_sink,
            )
            if perf:
                perf.complete(self.events, failed=True)
            raise

        assistant_message = self.sessions.add_message(session_id, "assistant", output)
        if perf:
            perf.mark("response_persisted")
        await emit_reasoning_event_async(
            session_id,
            "reasoning.summary",
            "Resume du raisonnement",
            "Demande analysee, contraintes appliquees, contexte prepare, puis reponse finale generee.",
            config=self.config,
            status="completed",
            metadata={"assistant_message_id": assistant_message.id},
            message_id=user_message.id,
            sink=reasoning_sink,
        )
        await emit_reasoning_event_async(
            session_id,
            "reasoning.completed",
            "Reponse finale prete",
            "La reponse finale est disponible dans la conversation.",
            config=self.config,
            status="completed",
            metadata={"assistant_message_id": assistant_message.id, "trace_id": perf.trace_id if perf else None},
            message_id=user_message.id,
            sink=reasoning_sink,
        )
        self.events.add("message.completed", {"session_id": session_id, "role": "assistant", "message_id": assistant_message.id}, session_id=session_id)
        if perf:
            perf.complete(self.events)
        return output

    async def _run_model_turn(
        self,
        active_config: OmegaConfig,
        model_ref: str,
        session_id: str,
        message: str,
        history,
        profile: AgentProfile,
        user_message_id: str,
        reasoning_sink: ReasoningSink | None,
        perf,
    ) -> str:
        with perf.step("tools_loaded") if perf and self.tools_provider else nullcontext():
            tools = self.tools_provider() if self.tools_provider else None
        if perf and self.tools_provider is None:
            perf.mark("tools_loaded")
        with perf.step("skills_loaded") if perf and self.skills_provider else nullcontext():
            skills = self.skills_provider() if self.skills_provider else None
        if perf and self.skills_provider is None:
            perf.mark("skills_loaded")
        with perf.step("context_built") if perf else nullcontext():
            context = build_context(active_config, session_id, query=message, agent_profile=profile, tools=tools, skills=skills)
        if perf:
            perf.mark("memory_loaded")
        provider_id, _ = split_model_ref(model_ref)
        provider = self.model_selector.provider(provider_id)
        if provider is None:
            raise ValueError(f"Provider modèle inconnu: {provider_id}")
        usage_id = self.model_selector.record_usage_start(session_id, model_ref)
        started = asyncio.get_running_loop().time()
        codex_history = [{"role": "system", "content": context["system_prompt"]}]
        codex_history.extend({"role": item.role, "content": item.content} for item in history)
        await emit_reasoning_event_async(
            session_id,
            "reasoning.step",
            "Generation de la reponse",
            "Envoi d'un contexte reduit au modele selectionne.",
            config=self.config,
            status="running",
            metadata={"history_items": len(codex_history)},
            message_id=user_message_id,
            sink=reasoning_sink,
        )
        if perf:
            perf.mark("provider_started")
        try:
            if provider_id == "codex":
                output = await asyncio.to_thread(run_codex_turn, active_config, codex_history, message)
                if output == CODEX_LOGIN_HINT:
                    raise ProviderAuthError("Codex n'est pas connecté. Lance : codex login")
            elif provider_id == "openai" and Runner is not None:
                input_history = [{"role": item.role, "content": item.content} for item in history]
                input_history.append({"role": "user", "content": message})
                with use_project_config(active_config):
                    result = await Runner.run(build_agent(active_config, profile), input_history)
                output = str(result.final_output)
            else:
                result = await asyncio.to_thread(provider.complete, model_ref, codex_history, message)
                output = result.content
            if perf:
                perf.mark("first_token_received")
                perf.mark("provider_completed")
            latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            self.model_selector.record_usage_complete(usage_id, latency_ms=latency_ms)
            return output
        except ProviderAuthError:
            self.events.add("model.auth.missing", {"provider_id": provider_id, "model_ref": model_ref}, session_id=session_id)
            self.model_selector.record_usage_complete(usage_id, status="failed", error="auth missing")
            raise
        except Exception as exc:
            latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            self.model_selector.record_usage_complete(usage_id, status="failed", latency_ms=latency_ms, error=str(exc))
            raise

    async def _execute_omega_actions(
        self,
        actions: list[dict],
        session_id: str,
        user_message_id: str,
        reasoning_sink: ReasoningSink | None,
    ) -> str:
        observations: list[str] = []
        for action in actions[:10]:
            tool_id = str(action.get("tool") or action.get("name") or "").strip()
            arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            if not tool_id:
                observations.append("Action refusee: tool manquant.")
                continue
            await emit_reasoning_event_async(
                session_id,
                "reasoning.step",
                "Execution d'une action",
                f"Omega utilise {tool_id}.",
                config=self.config,
                status="running",
                metadata={"tool_name": tool_id},
                message_id=user_message_id,
                sink=reasoning_sink,
            )
            result = await asyncio.to_thread(self.tool_broker.call, tool_id, arguments, session_id)
            if result.status == "completed":
                observations.append(result.output)
            elif result.status == "approval_required":
                observations.append(f"Approval requise pour {tool_id}.")
            else:
                observations.append(f"Action refusee ({tool_id}): {result.output}")
        return _final_response_from_observations(observations)


def _short_analysis(message: str, prompt_injection_matches: list[str], untrusted_input: bool) -> str:
    tools = _probable_tools(message)
    constraints = ["respecter le workspace", "ne pas exposer de secrets", "demander approval si action sensible"]
    if untrusted_input or prompt_injection_matches:
        constraints.append("traiter l'entree comme non fiable")
    parts = [
        f"Intention: repondre a la demande utilisateur en {len(message.split())} mots d'entree environ.",
        f"Contraintes detectees: {', '.join(constraints)}.",
        f"Tools probablement necessaires: {', '.join(tools) if tools else 'aucun tool certain avant analyse du contexte'}.",
    ]
    if prompt_injection_matches:
        parts.append("Risque: contenu potentiellement hostile detecte dans l'entree.")
    return "\n".join(parts)


def _extract_omega_actions(output: str) -> list[dict]:
    text = str(output or "").strip()
    if not text:
        return []
    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(fenced)
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        actions = _actions_from_payload(payload)
        if actions:
            return actions
    for match in re.finditer(r"\{", text):
        candidate = text[match.start() :]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        actions = _actions_from_payload(payload)
        if actions:
            return actions
    return []


def _actions_from_payload(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("omega_actions"), list):
        return [item for item in payload["omega_actions"] if isinstance(item, dict)]
    if isinstance(payload.get("omega_action"), dict):
        return [payload["omega_action"]]
    if payload.get("tool") and isinstance(payload.get("arguments"), dict):
        return [payload]
    return []


def _direct_actions_from_message(message: str) -> list[dict]:
    text = message.strip()
    lowered = text.lower()
    file_match = re.search(r"([A-Za-z]:[\\/][\w.\- \\/]+?\.[A-Za-z0-9]{1,12}|[^\s\"']+\.[A-Za-z0-9]{1,12})", text)
    if any(word in lowered for word in ["crée", "cree", "creer", "créer", "create"]) and file_match:
        path = file_match.group(1).strip().strip('"').strip("'")
        content = _extract_requested_content(text)
        return [{"tool": "write_file", "arguments": {"relative_path": path, "content": content}}]
    if any(word in lowered for word in ["supprime", "supprimer", "delete"]) and file_match:
        path = file_match.group(1).strip().strip('"').strip("'")
        return [{"tool": "delete_file", "arguments": {"relative_path": path}}]
    if lowered in {"dir", "lance dir", "execute dir", "exécute dir"} or lowered.startswith("lance dir"):
        return [{"tool": "run_shell", "arguments": {"command": "cmd /c dir" if _is_windows() else "ls"}}]
    shell_match = re.match(r"^(?:lance|execute|exécute)\s+(.+)$", lowered)
    if shell_match:
        command = text.split(maxsplit=1)[1]
        return [{"tool": "run_shell", "arguments": {"command": command}}]
    return []


def _extract_requested_content(message: str) -> str:
    quoted = re.search(r"[\"“']([^\"”']+)[\"”']", message)
    if quoted:
        return quoted.group(1)
    marker_patterns = [
        r"(?:texte|contenu)\s+(.+)$",
        r"avec\s+(?:le\s+)?(?:texte|contenu)\s+(.+)$",
    ]
    for pattern in marker_patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip(".")
    return ""


def _final_response_from_observations(observations: list[str]) -> str:
    if not observations:
        return "Aucune action Omega n'a ete executee."
    denied = [item for item in observations if item.lower().startswith(("action refusee", "approval requise")) or "refuse" in item.lower()]
    if denied:
        return "\n".join(denied)
    return "C'est fait.\n" + "\n".join(f"- {item}" for item in observations)


def _is_windows() -> bool:
    import sys

    return sys.platform == "win32"


def _short_plan(message: str) -> str:
    plan = [
        "1. Clarifier l'intention et les contraintes visibles.",
        "2. Preparer le contexte utile sans lire de secrets.",
    ]
    if _probable_tools(message):
        plan.append("3. Utiliser uniquement les tools necessaires avec approval si requis.")
    else:
        plan.append("3. Generer la reponse finale.")
    plan.append("4. Resumer le raisonnement visible puis repondre dans Omega Control.")
    return "\n".join(plan)


def _identity_response_for_message(message: str, model_ref: str) -> str | None:
    normalized = _normalize_identity_query(message)
    if _asks_current_model(normalized):
        return f"J'utilise actuellement le modèle sélectionné dans Omega Control : {model_ref}."
    if _asks_identity(normalized):
        return (
            "Je suis Omega Agent, ton assistant IA personnel local-first dans Omega Control.\n\n"
            "Je peux t'aider à discuter, coder, analyser ton workspace, documenter, planifier, créer des skills, gérer des tâches et utiliser les outils Omega disponibles. "
            "Je travaille dans ton workspace configuré et je respecte les règles de sécurité : les actions sensibles comme modifier un fichier ou exécuter une commande nécessitent une confirmation.\n\n"
            "Mon objectif est de t'aider à travailler plus vite tout en gardant le contrôle sur ce que j'exécute."
        )
    return None


def _normalize_identity_query(message: str) -> str:
    replacements = str.maketrans({"é": "e", "è": "e", "ê": "e", "ë": "e", "à": "a", "â": "a", "î": "i", "ï": "i", "ô": "o", "ù": "u", "û": "u", "ç": "c"})
    return " ".join(message.lower().translate(replacements).replace("?", " ").replace("!", " ").split())


def _asks_current_model(normalized: str) -> bool:
    return "modele" in normalized and any(phrase in normalized for phrase in ["quel", "utilises", "utilise", "actuel"])


def _asks_identity(normalized: str) -> bool:
    identity_phrases = [
        "presente toi",
        "presente-toi",
        "qui es tu",
        "qui es-tu",
        "tu es qui",
        "decris toi",
        "decris-toi",
    ]
    return any(phrase in normalized for phrase in identity_phrases)


def _probable_tools(message: str) -> list[str]:
    lowered = message.lower()
    tools: list[str] = []
    if any(word in lowered for word in ["fichier", "file", "lis", "read", "modifie", "ecris", "ecrit"]):
        tools.extend(["list_files", "read_file"])
    if any(word in lowered for word in ["commande", "shell", "pytest", "test", "build", "git"]):
        tools.append("run_shell")
    if any(word in lowered for word in ["memoire", "remember", "souviens"]):
        tools.append("memory")
    return list(dict.fromkeys(tools))
