from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact
from omega_agent.skills.skill_models import (
    CANDIDATE_STATUSES,
    SKILL_STATUSES,
    SKILL_TYPES,
    TEST_STATUSES,
    SkillCandidate,
    SkillTestRun,
    SkillVersion,
    StoredSkill,
    parse_json,
)


class SkillStore:
    def __init__(self, config: OmegaConfig):
        self.config = config
        with connect_runtime_db(config):
            pass

    def create_candidate(
        self,
        *,
        title: str,
        description: str,
        source_run_ids: list[str],
        source_workflow_ids: list[str] | None,
        detected_pattern: dict[str, Any],
        proposed_skill: dict[str, Any],
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> SkillCandidate:
        now = _now()
        candidate_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO skill_candidates(
                    id, title, description, source_run_ids_json, source_workflow_ids_json,
                    detected_pattern_json, proposed_skill_json, confidence, status,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    candidate_id,
                    str(title)[:200],
                    str(description)[:2000],
                    _json(source_run_ids),
                    _json(source_workflow_ids or []),
                    _json(detected_pattern),
                    _json(proposed_skill),
                    max(0.0, min(1.0, float(confidence))),
                    now,
                    now,
                    _json(metadata or {}),
                ),
            )
        return self.get_candidate(candidate_id)

    def get_candidate(self, candidate_id: str) -> SkillCandidate | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM skill_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return _candidate(row) if row else None

    def list_candidates(self, status: str | None = None, limit: int = 100) -> list[SkillCandidate]:
        query = "SELECT * FROM skill_candidates"
        params: list[Any] = []
        if status:
            if status not in CANDIDATE_STATUSES:
                raise ValueError("Statut candidate invalide.")
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [_candidate(row) for row in rows]

    def update_candidate_status(self, candidate_id: str, status: str) -> SkillCandidate | None:
        if status not in CANDIDATE_STATUSES:
            raise ValueError("Statut candidate invalide.")
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE skill_candidates SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), candidate_id))
        return self.get_candidate(candidate_id)

    def candidate_by_fingerprint(self, fingerprint: str) -> SkillCandidate | None:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                "SELECT * FROM skill_candidates WHERE status IN ('pending','accepted','promoted') ORDER BY updated_at DESC"
            ).fetchall()
        for row in rows:
            candidate = _candidate(row)
            if candidate.metadata.get("fingerprint") == fingerprint:
                return candidate
        return None

    def create_skill(
        self,
        *,
        name: str,
        description: str,
        skill_type: str,
        definition: dict[str, Any],
        test_cases: list[dict[str, Any]],
        source_candidate_id: str | None = None,
        status: str = "draft",
        metadata: dict[str, Any] | None = None,
    ) -> StoredSkill:
        if status not in SKILL_STATUSES or skill_type not in SKILL_TYPES:
            raise ValueError("Type ou statut de skill invalide.")
        now = _now()
        skill_id = uuid4().hex
        slug = _unique_slug(self.config, name)
        allowed_tools = list(definition.get("required_capabilities") or [])
        risk_level = str((definition.get("safety_policy") or {}).get("risk_level") or "low")
        enabled = status == "active"
        metadata = {"foundry": True, **(metadata or {})}
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO skills(
                    id, name, slug, description, version, status, skill_type,
                    definition_json, test_cases_json, source_candidate_id,
                    created_at, updated_at, metadata_json, risk_level, enabled,
                    allowed_tools_json, tags_json, path
                ) VALUES (?, ?, ?, ?, '0.1.0', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    str(name)[:160],
                    slug,
                    str(description)[:2000],
                    status,
                    skill_type,
                    _json(definition),
                    _json(test_cases),
                    source_candidate_id,
                    now,
                    now,
                    _json(metadata),
                    risk_level if risk_level in {"low", "medium", "high", "critical"} else "medium",
                    1 if enabled else 0,
                    _json(allowed_tools),
                    _json(["foundry", skill_type]),
                    f"db://skills/{skill_id}",
                ),
            )
            conn.execute(
                """
                INSERT INTO skill_versions(id, skill_id, version, definition_json, changelog, created_at, metadata_json)
                VALUES (?, ?, '0.1.0', ?, 'Initial Foundry draft', ?, ?)
                """,
                (uuid4().hex, skill_id, _json(definition), now, _json({"source_candidate_id": source_candidate_id})),
            )
        return self.get_skill(skill_id)

    def get_skill(self, skill_id_or_slug: str) -> StoredSkill | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(
                """
                SELECT * FROM skills
                WHERE id = ? OR slug = ?
                ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END LIMIT 1
                """,
                (skill_id_or_slug, skill_id_or_slug, skill_id_or_slug),
            ).fetchone()
        if not row:
            return None
        skill = _skill(row)
        return skill if skill.metadata.get("foundry") or skill.definition else None

    def list_skills(self, status: str | None = None, limit: int = 200) -> list[StoredSkill]:
        query = "SELECT * FROM skills"
        params: list[Any] = []
        if status:
            if status not in SKILL_STATUSES:
                raise ValueError("Statut skill invalide.")
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        skills = [_skill(row) for row in rows]
        return [skill for skill in skills if skill.metadata.get("foundry") or skill.definition]

    def update_skill(self, skill_id: str, patch: dict[str, Any], *, changelog: str = "Skill updated") -> StoredSkill | None:
        current = self.get_skill(skill_id)
        if current is None:
            return None
        definition = patch.get("definition") if isinstance(patch.get("definition"), dict) else current.definition
        tests = patch.get("test_cases") if isinstance(patch.get("test_cases"), list) else current.test_cases
        name = str(patch.get("name") or current.name)
        description = str(patch.get("description") or current.description)
        skill_type = str(patch.get("skill_type") or current.skill_type)
        if skill_type not in SKILL_TYPES:
            raise ValueError("Type de skill invalide.")
        next_version = _bump_patch(current.version)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE skills SET name = ?, description = ?, skill_type = ?, version = ?,
                    definition_json = ?, test_cases_json = ?, updated_at = ? WHERE id = ?
                """,
                (name, description, skill_type, next_version, _json(definition), _json(tests), now, current.id),
            )
            conn.execute(
                """
                INSERT INTO skill_versions(id, skill_id, version, definition_json, changelog, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, '{}')
                """,
                (uuid4().hex, current.id, next_version, _json(definition), str(changelog)[:1000], now),
            )
        return self.get_skill(current.id)

    def set_status(self, skill_id: str, status: str) -> StoredSkill | None:
        if status not in SKILL_STATUSES:
            raise ValueError("Statut skill invalide.")
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "UPDATE skills SET status = ?, enabled = ?, updated_at = ? WHERE id = ?",
                (status, 1 if status == "active" else 0, _now(), skill_id),
            )
        return self.get_skill(skill_id)

    def archive_skill(self, skill_id: str) -> bool:
        return self.set_status(skill_id, "archived") is not None

    def list_versions(self, skill_id: str) -> list[SkillVersion]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC", (skill_id,)).fetchall()
        return [_version(row) for row in rows]

    def add_test_run(
        self,
        skill_id: str,
        version: str,
        status: str,
        results: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> SkillTestRun:
        if status not in TEST_STATUSES:
            raise ValueError("Statut de test invalide.")
        test_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                INSERT INTO skill_test_runs(id, skill_id, version, status, results_json, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (test_id, skill_id, version, status, _json(results), _now(), _json(metadata or {})),
            )
        return self.get_test_run(test_id)

    def get_test_run(self, test_id: str) -> SkillTestRun | None:
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM skill_test_runs WHERE id = ?", (test_id,)).fetchone()
        return _test(row) if row else None

    def list_test_runs(self, skill_id: str) -> list[SkillTestRun]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM skill_test_runs WHERE skill_id = ? ORDER BY created_at DESC", (skill_id,)).fetchall()
        return [_test(row) for row in rows]

    def latest_test_run(self, skill_id: str, version: str | None = None) -> SkillTestRun | None:
        query = "SELECT * FROM skill_test_runs WHERE skill_id = ?"
        params: list[Any] = [skill_id]
        if version:
            query += " AND version = ?"
            params.append(version)
        query += " ORDER BY created_at DESC LIMIT 1"
        with connect_runtime_db(self.config) as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return _test(row) if row else None


def _candidate(row) -> SkillCandidate:
    return SkillCandidate(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        source_run_ids=parse_json(row["source_run_ids_json"], []),
        source_workflow_ids=parse_json(row["source_workflow_ids_json"], []),
        detected_pattern=parse_json(row["detected_pattern_json"], {}),
        proposed_skill=parse_json(row["proposed_skill_json"], {}),
        confidence=float(row["confidence"] or 0),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _skill(row) -> StoredSkill:
    definition = parse_json(row["definition_json"], {})
    metadata = parse_json(row["metadata_json"], {})
    return StoredSkill(
        id=row["id"],
        name=row["name"],
        slug=row["slug"] or row["id"],
        description=row["description"],
        version=row["version"],
        status=row["status"] or ("active" if row["enabled"] else "disabled"),
        skill_type=row["skill_type"] or "prompt",
        definition=definition,
        test_cases=parse_json(row["test_cases_json"], []),
        source_candidate_id=row["source_candidate_id"],
        created_at=row["created_at"] or row["updated_at"],
        updated_at=row["updated_at"],
        metadata=metadata,
        risk_level=row["risk_level"] or "low",
        enabled=bool(row["enabled"]) and (row["status"] or "active") == "active",
        allowed_tools=parse_json(row["allowed_tools_json"], list(definition.get("required_capabilities") or [])),
    )


def _version(row) -> SkillVersion:
    return SkillVersion(
        id=row["id"],
        skill_id=row["skill_id"],
        version=row["version"],
        definition=parse_json(row["definition_json"], {}),
        changelog=row["changelog"],
        created_at=row["created_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _test(row) -> SkillTestRun:
    return SkillTestRun(
        id=row["id"],
        skill_id=row["skill_id"],
        version=row["version"],
        status=row["status"],
        results=parse_json(row["results_json"], {}),
        created_at=row["created_at"],
        metadata=parse_json(row["metadata_json"], {}),
    )


def _json(value: Any) -> str:
    return json.dumps(redact(value), ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return (normalized or "omega-skill")[:80]


def _unique_slug(config: OmegaConfig, value: str) -> str:
    base = _slug(value)
    slug = base
    suffix = 2
    with connect_runtime_db(config) as conn:
        while conn.execute("SELECT 1 FROM skills WHERE slug = ? OR id = ?", (slug, slug)).fetchone():
            slug = f"{base[:72]}-{suffix}"
            suffix += 1
    return slug


def _bump_patch(version: str) -> str:
    parts = str(version or "0.1.0").split(".")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return "0.1.1"
    return f"{major}.{minor}.{patch + 1}"
