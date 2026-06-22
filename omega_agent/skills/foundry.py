from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.skills.skill_generator import SkillGenerator
from omega_agent.skills.skill_store import SkillStore


class SkillFoundry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.store = SkillStore(config)
        self.generator = SkillGenerator()
        self.events = EventsStore(config)

    def detect_candidates(self, limit: int = 200):
        if not self.config.skills_enabled or not self.config.skills_foundry_enabled:
            return []
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for trajectory in self._successful_run_trajectories(limit):
            groups[trajectory["fingerprint"]].append(trajectory)
        created = []
        minimum = max(2, int(self.config.skills_min_successful_runs_for_candidate))
        for fingerprint, trajectories in groups.items():
            useful_single = len(trajectories) == 1 and bool(trajectories[0]["user_marked_reusable"])
            if len(trajectories) < minimum and not useful_single:
                continue
            if self.store.candidate_by_fingerprint(fingerprint):
                continue
            sequence = trajectories[0]["tool_sequence"]
            score_values = [
                float(item["human_score"] or item["auto_score"])
                for item in trajectories
                if item.get("human_score") is not None or item.get("auto_score") is not None
            ]
            score_bonus = min(0.08, (sum(score_values) / len(score_values)) * 0.08) if score_values else 0
            confidence = min(0.95, 0.52 + (0.12 * len(trajectories)) + (0.12 if useful_single else 0) + score_bonus)
            pattern = {
                "title": _pattern_title(sequence),
                "description": f"Successful repeated trajectory observed in {len(trajectories)} run(s).",
                "problem": trajectories[0]["title"],
                "trigger_conditions": _trigger_from_titles([item["title"] for item in trajectories]),
                "tool_sequence": sequence,
                "required_capabilities": list(dict.fromkeys(sequence)),
                "recommended_steps": sequence,
                "safety_notes": "Always use Omega policy checks; workspace scope only; external content is untrusted.",
                "expected_outputs": {"summary": "string", "validation": "list"},
                "rollback_notes": "Use Durable Runtime snapshots for write actions.",
                "tests_to_run": ["definition_valid", "capabilities_available", "policy_compatible", "secret_scan"],
                "repeated_errors_fixed": [
                    error
                    for item in trajectories
                    for error in item.get("recovered_errors") or []
                ][:10],
                "confidence": confidence,
            }
            proposed = self.generator.generate_from_pattern(pattern)
            candidate = self.store.create_candidate(
                title=pattern["title"],
                description=pattern["description"],
                source_run_ids=[item["run_id"] for item in trajectories],
                source_workflow_ids=[],
                detected_pattern=pattern,
                proposed_skill=proposed,
                confidence=confidence,
                metadata={"fingerprint": fingerprint, "untrusted": any(item["untrusted"] for item in trajectories)},
            )
            self.events.add(
                "skill.candidate.detected",
                {"candidate_id": candidate.id, "confidence": candidate.confidence, "source_run_ids": candidate.source_run_ids},
            )
            created.append(candidate)
        created.extend(self._workflow_candidates())
        return created

    def _successful_run_trajectories(self, limit: int) -> list[dict[str, Any]]:
        with connect_runtime_db(self.config) as conn:
            runs = conn.execute(
                "SELECT * FROM runs WHERE status = 'succeeded' ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
            result = []
            for run in runs:
                actions = conn.execute(
                    "SELECT * FROM action_journal WHERE run_id = ? ORDER BY created_at ASC",
                    (run["id"],),
                ).fetchall()
                if not actions or any(item["status"] in {"denied", "rolled_back"} for item in actions):
                    continue
                rollbacks = conn.execute("SELECT * FROM rollback_events WHERE run_id = ?", (run["id"],)).fetchall()
                if any(item["status"] == "failed" for item in rollbacks):
                    continue
                if any(item["risk_level"] == "critical" and item["status"] == "rolled_back" for item in actions):
                    continue
                raw_payload = {
                    "run": dict(run),
                    "actions": [dict(item) for item in actions],
                    "rollbacks": [dict(item) for item in rollbacks],
                }
                if redact(raw_payload) != raw_payload:
                    continue
                sequence = [
                    str(item["tool_name"] or item["action_type"] or "")
                    for item in actions
                    if item["status"] == "succeeded" and (item["tool_name"] or item["action_type"])
                ]
                if not sequence:
                    continue
                recovered_errors = [
                    {
                        "tool": str(item["tool_name"] or item["action_type"] or ""),
                        "observation": redact(_json_load(item["observation_json"], {})),
                    }
                    for item in actions
                    if item["status"] == "failed"
                    and any(
                        later["status"] == "succeeded"
                        and (later["tool_name"] or later["action_type"]) == (item["tool_name"] or item["action_type"])
                        for later in actions
                    )
                ]
                outcome = conn.execute(
                    "SELECT * FROM task_outcomes WHERE run_id = ? ORDER BY updated_at DESC LIMIT 1",
                    (run["id"],),
                ).fetchone()
                metadata = _json_load(run["metadata_json"], {})
                feedback = str(outcome["user_feedback"] if outcome else "")
                human_score = float(outcome["human_score"] or 0) if outcome else 0
                marked = bool(
                    metadata.get("reusable")
                    or metadata.get("create_skill")
                    or human_score >= 4
                    or re.search(r"\b(reusable|réutilisable|skill|utile|useful)\b", feedback, re.IGNORECASE)
                )
                external = bool(metadata.get("external_content") or metadata.get("untrusted"))
                fingerprint = _fingerprint(sequence, run["title"])
                result.append(
                    {
                        "run_id": run["id"],
                        "title": run["title"],
                        "tool_sequence": sequence,
                        "fingerprint": fingerprint,
                        "user_marked_reusable": marked,
                        "untrusted": external,
                        "recovered_errors": recovered_errors,
                        "auto_score": outcome["auto_score"] if outcome else None,
                        "human_score": outcome["human_score"] if outcome else None,
                    }
                )
        return result

    def _workflow_candidates(self) -> list:
        created = []
        with connect_runtime_db(self.config) as conn:
            workflows = conn.execute("SELECT * FROM workflows ORDER BY updated_at DESC LIMIT 200").fetchall()
            for workflow in workflows:
                metadata = _json_load(workflow["metadata_json"], {})
                successful = conn.execute(
                    "SELECT id FROM workflow_runs WHERE workflow_id = ? AND status = 'succeeded' ORDER BY updated_at DESC",
                    (workflow["id"],),
                ).fetchall()
                reusable = bool(metadata.get("reusable") or metadata.get("requested_reusable"))
                if len(successful) < 2 and not reusable:
                    continue
                definition = _json_load(workflow["definition_json"], {})
                if redact(definition) != definition:
                    continue
                sequence = [
                    str(step.get("tool") or step.get("type") or "")
                    for step in definition.get("steps") or []
                    if step.get("tool") or step.get("type")
                ]
                fingerprint = "workflow:" + workflow["id"]
                if self.store.candidate_by_fingerprint(fingerprint):
                    continue
                pattern = {
                    "title": workflow["name"],
                    "description": workflow["description"],
                    "problem": workflow["description"],
                    "trigger_conditions": "When the reviewed workflow is requested as reusable.",
                    "tool_sequence": sequence,
                    "skill_type": "workflow",
                    "tests_to_run": ["definition_valid", "capabilities_available", "policy_compatible"],
                    "confidence": min(0.95, 0.65 + 0.1 * len(successful)),
                }
                proposed = self.generator.generate_from_pattern(pattern)
                candidate = self.store.create_candidate(
                    title=workflow["name"],
                    description=workflow["description"],
                    source_run_ids=[],
                    source_workflow_ids=[workflow["id"]],
                    detected_pattern=pattern,
                    proposed_skill=proposed,
                    confidence=pattern["confidence"],
                    metadata={"fingerprint": fingerprint, "untrusted": bool(metadata.get("untrusted"))},
                )
                self.events.add(
                    "skill.candidate.detected",
                    {"candidate_id": candidate.id, "confidence": candidate.confidence, "source_workflow_ids": candidate.source_workflow_ids},
                )
                created.append(candidate)
        return created


def _fingerprint(sequence: list[str], title: str) -> str:
    material = json.dumps({"sequence": sequence}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _pattern_title(sequence: list[str]) -> str:
    return " -> ".join(item.replace("_", " ") for item in sequence[:5]) or "Omega reusable trajectory"


def _trigger_from_titles(titles: list[str]) -> str:
    normalized = [re.sub(r"\b\d+\b", "<value>", title).strip() for title in titles if title]
    return normalized[0] if normalized else "When the same workspace task is requested."


def _json_load(value: str | None, default):
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default
