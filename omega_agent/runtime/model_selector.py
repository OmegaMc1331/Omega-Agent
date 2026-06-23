from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from omega_agent.config import OmegaConfig
from omega_agent.config_store import load_config, save_config, set_config_value
from omega_agent.providers.base import AuthStatus, ModelInfo, ProviderInfo
from omega_agent.providers.registry import ProviderRegistry
from omega_agent.providers.thinking import (
    matrix_for_config,
    save_thinking_level,
    thinking_status,
)
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.security.redaction import redact

VALID_SCOPES = {"global", "project", "session", "agent_profile"}


@dataclass(frozen=True)
class ModelPreference:
    id: str
    scope: str
    scope_id: str | None
    primary_model_ref: str
    fallback_model_ref: str | None
    created_at: str
    updated_at: str

    def as_api(self) -> dict:
        return redact(asdict(self))


@dataclass(frozen=True)
class ResolvedModel:
    primary_model_ref: str
    fallback_model_ref: str | None
    provider_id: str
    model_name: str
    source_scope: str
    source_scope_id: str | None

    def as_api(self) -> dict:
        return redact(asdict(self))


class ModelSelector:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.providers = ProviderRegistry(config)
        self._status_cache: tuple[float, list[dict]] | None = None
        with connect_runtime_db(config):
            pass
        self.seed_defaults()

    def seed_defaults(self) -> None:
        now = _now()
        with connect_runtime_db(self.config) as conn:
            for provider in self.providers.list():
                info = provider.info()
                conn.execute(
                    """
                    INSERT INTO model_providers(id, name, description, auth_type, enabled, status, config_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        auth_type=excluded.auth_type,
                        enabled=excluded.enabled,
                        config_json=excluded.config_json,
                        updated_at=excluded.updated_at
                    """,
                    (info.id, info.name, info.description, info.auth_type, int(info.enabled), info.status, json.dumps(info.config_schema), now, now),
                )
                for model in provider.list_models():
                    self._upsert_model(conn, model, now)
            self._ensure_global_default(conn, now)

    def _ensure_global_default(self, conn, now: str) -> None:
        existing = conn.execute("SELECT id FROM model_preferences WHERE scope = 'global' AND scope_id IS NULL").fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO model_preferences(id, scope, scope_id, primary_model_ref, fallback_model_ref, created_at, updated_at)
                VALUES (?, 'global', NULL, ?, ?, ?, ?)
                """,
                (uuid4().hex, self.config.default_model_ref, self.config.fallback_model_ref or None, now, now),
            )
        elif self.config.model_config_source == "config.json":
            conn.execute(
                """
                UPDATE model_preferences
                SET primary_model_ref = ?, fallback_model_ref = ?, updated_at = ?
                WHERE id = ?
                """,
                (self.config.default_model_ref, self.config.fallback_model_ref or None, now, existing["id"]),
            )

    def _upsert_model(self, conn, model: ModelInfo, now: str) -> None:
        capabilities = {
            "supports_streaming": model.supports_streaming,
            "supports_tools": model.supports_tools,
            "supports_vision": model.supports_vision,
            "supports_json": model.supports_json,
            "supports_reasoning": model.supports_reasoning,
            "supports_local": model.supports_local,
            "recommended_for": model.recommended_for,
        }
        conn.execute(
            """
            INSERT INTO model_catalog(
                id, provider_id, model_ref, display_name, description, context_window,
                max_output_tokens, capabilities_json, speed_tier, cost_tier, enabled,
                available, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_ref) DO UPDATE SET
                display_name=excluded.display_name,
                description=excluded.description,
                context_window=excluded.context_window,
                max_output_tokens=excluded.max_output_tokens,
                capabilities_json=excluded.capabilities_json,
                speed_tier=excluded.speed_tier,
                cost_tier=excluded.cost_tier,
                available=excluded.available,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                model.id,
                model.provider_id,
                model.ref,
                model.display_name,
                model.description,
                model.context_window,
                model.max_output_tokens,
                json.dumps(capabilities, ensure_ascii=False),
                model.speed_tier,
                model.cost_tier,
                int(model.enabled),
                int(model.available),
                json.dumps(model.metadata, ensure_ascii=False),
                now,
                now,
            ),
        )

    def providers_api(self) -> list[dict]:
        statuses = {item["provider_id"]: item for item in self.status_api()}
        return [
            redact(
                {
                    **provider.info().as_api(),
                    "status": statuses.get(provider.provider_id, {}).get("status", "unknown"),
                }
            )
            for provider in self.providers.list()
        ]

    def catalog_api(self) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM model_catalog ORDER BY provider_id, display_name").fetchall()
        result = []
        for row in rows:
            capabilities = json.loads(row["capabilities_json"] or "{}")
            metadata = json.loads(row["metadata_json"] or "{}")
            thinking = self.thinking_api(str(row["model_ref"]))
            result.append(
                redact(
                    {
                        "id": row["id"],
                        "provider_id": row["provider_id"],
                        "model_ref": row["model_ref"],
                        "ref": row["model_ref"],
                        "display_name": row["display_name"],
                        "description": row["description"],
                        "context_window": row["context_window"],
                        "max_output_tokens": row["max_output_tokens"],
                        **capabilities,
                        "capabilities": capabilities,
                        "speed_tier": row["speed_tier"],
                        "cost_tier": row["cost_tier"],
                        "enabled": bool(row["enabled"]),
                        "available": bool(row["available"]),
                        "metadata": metadata,
                        "metadata_json": row["metadata_json"],
                        "thinking": thinking,
                    }
                )
            )
        return result

    def preferences_api(self) -> list[dict]:
        return [item.as_api() for item in self.list_preferences()]

    def usage_api(self, limit: int = 50) -> list[dict]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, provider_id, model_ref, started_at, completed_at,
                       status, latency_ms, input_tokens, output_tokens, error, metadata_json
                FROM model_usage_events
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                redact(
                    {
                        "id": row["id"],
                        "session_id": row["session_id"],
                        "provider_id": row["provider_id"],
                        "model_ref": row["model_ref"],
                        "started_at": row["started_at"],
                        "completed_at": row["completed_at"],
                        "status": row["status"],
                        "latency_ms": row["latency_ms"],
                        "input_tokens": row["input_tokens"],
                        "output_tokens": row["output_tokens"],
                        "error": row["error"],
                        "metadata": json.loads(row["metadata_json"] or "{}"),
                    }
                )
            )
        return result

    def list_preferences(self) -> list[ModelPreference]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM model_preferences ORDER BY scope, scope_id").fetchall()
        return [self._preference_from_row(row) for row in rows]

    def set_preference(self, scope: str, primary_model_ref: str, scope_id: str | None = None, fallback_model_ref: str | None = None) -> ModelPreference:
        if scope not in VALID_SCOPES:
            raise ValueError("Scope modèle invalide.")
        self._validate_model_ref(primary_model_ref)
        if fallback_model_ref:
            self._validate_model_ref(fallback_model_ref)
        if scope == "global" and scope_id is None and self.config.config_path is not None:
            data = set_config_value("models.default", primary_model_ref, file_path=self.config.config_path)
            data = set_config_value("models.fallback", fallback_model_ref or None, data)
            recent = list(data.get("models", {}).get("recent") or [])
            recent = [primary_model_ref, *[item for item in recent if item != primary_model_ref]][:10]
            data = set_config_value("models.recent", recent, data)
            save_config(data, self.config.config_path)
        now = _now()
        with connect_runtime_db(self.config) as conn:
            existing = conn.execute("SELECT * FROM model_preferences WHERE scope = ? AND scope_id IS ?", (scope, scope_id)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE model_preferences SET primary_model_ref = ?, fallback_model_ref = ?, updated_at = ? WHERE id = ?",
                    (primary_model_ref, fallback_model_ref, now, existing["id"]),
                )
                row = conn.execute("SELECT * FROM model_preferences WHERE id = ?", (existing["id"],)).fetchone()
            else:
                preference_id = uuid4().hex
                conn.execute(
                    """
                    INSERT INTO model_preferences(id, scope, scope_id, primary_model_ref, fallback_model_ref, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (preference_id, scope, scope_id, primary_model_ref, fallback_model_ref, now, now),
                )
                row = conn.execute("SELECT * FROM model_preferences WHERE id = ?", (preference_id,)).fetchone()
        return self._preference_from_row(row)

    def resolve_model(self, session_id: str | None = None, project_id: str | None = None, agent_profile_id: str | None = None) -> ResolvedModel:
        preference = (
            self._get_preference("session", session_id)
            or self._get_preference("project", project_id)
            or self._get_preference("agent_profile", agent_profile_id)
            or self._get_preference("global", None)
        )
        if preference is None:
            primary = self.config.default_model_ref
            fallback = self.config.fallback_model_ref or None
            scope = "env"
            scope_id = None
        else:
            primary = preference.primary_model_ref
            fallback = preference.fallback_model_ref
            scope = preference.scope
            scope_id = preference.scope_id
        provider_id, model_name = split_model_ref(primary)
        return ResolvedModel(primary, fallback, provider_id, model_name, scope, scope_id)

    def current_api(self, session_id: str | None = None, project_id: str | None = None, agent_profile_id: str | None = None) -> dict:
        payload = self.resolve_model(
            session_id=session_id,
            project_id=project_id,
            agent_profile_id=agent_profile_id,
        ).as_api()
        payload["default_provider"] = self._default_provider()
        payload["thinking"] = self.thinking_api(str(payload["primary_model_ref"]))
        return payload

    def thinking_api(self, model_ref: str) -> dict:
        return thinking_status(matrix_for_config(self.config), model_ref)

    def set_thinking_level(self, level: str, model_ref: str | None = None) -> dict:
        target_model = model_ref or self.resolve_model().primary_model_ref
        return save_thinking_level(self.config, level, model_ref=target_model if model_ref else None)

    def status_api(self, force: bool = False) -> list[dict]:
        now = time.monotonic()
        if not force and self._status_cache is not None:
            expires_at, payload = self._status_cache
            if now < expires_at:
                return payload
        statuses = []
        checked_at = _now()
        with connect_runtime_db(self.config) as conn:
            for provider in self.providers.list():
                status = provider.check_auth()
                statuses.append({"provider_id": status.provider_id, "status": status.status, "auth_method": status.auth_method, "last_checked_at": checked_at, "metadata": redact(status.metadata)})
                conn.execute(
                    """
                    INSERT INTO provider_auth_status(id, provider_id, status, auth_method, last_checked_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider_id) DO UPDATE SET
                        status=excluded.status,
                        auth_method=excluded.auth_method,
                        last_checked_at=excluded.last_checked_at,
                        metadata_json=excluded.metadata_json
                    """,
                    (uuid4().hex, status.provider_id, status.status, status.auth_method, checked_at, json.dumps(redact(status.metadata), ensure_ascii=False)),
                )
        self._status_cache = (now + self.config.model_status_cache_seconds, statuses)
        return statuses

    def refresh_catalog(self, provider_id: str | None = None) -> dict:
        now = _now()
        providers = [self.providers.get(provider_id)] if provider_id else self.providers.list()
        count = 0
        errors: list[dict[str, str]] = []
        with connect_runtime_db(self.config) as conn:
            for provider in providers:
                if provider is None:
                    if provider_id:
                        errors.append({"provider_id": provider_id, "error": "Provider introuvable."})
                    continue
                try:
                    models = provider.discover_models()
                except Exception as exc:
                    errors.append({"provider_id": provider.provider_id, "error": str(redact(str(exc)))})
                    models = provider.list_models()
                for model in models:
                    self._upsert_model(conn, model, now)
                    count += 1
        return {"count": count, "errors": errors}

    def provider(self, provider_id: str):
        return self.providers.get(provider_id)

    def _default_provider(self) -> str:
        if self.config.config_path is None or not self.config.config_path.exists():
            return self.config.provider
        data = load_config(self.config.config_path)
        return str(data.get("providers", {}).get("default") or self.config.provider)

    def record_usage_start(self, session_id: str | None, model_ref: str) -> str:
        provider_id, _ = split_model_ref(model_ref)
        usage_id = uuid4().hex
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                "INSERT INTO model_usage_events(id, session_id, provider_id, model_ref, started_at, status, metadata_json) VALUES (?, ?, ?, ?, ?, 'running', '{}')",
                (usage_id, session_id, provider_id, model_ref, _now()),
            )
        return usage_id

    def record_usage_complete(self, usage_id: str, status: str = "completed", latency_ms: int | None = None, input_tokens: int | None = None, output_tokens: int | None = None, error: str | None = None) -> None:
        with connect_runtime_db(self.config) as conn:
            conn.execute(
                """
                UPDATE model_usage_events
                SET completed_at = ?, status = ?, latency_ms = ?, input_tokens = ?, output_tokens = ?, error = ?
                WHERE id = ?
                """,
                (_now(), status, latency_ms, input_tokens, output_tokens, redact(error) if error else None, usage_id),
            )

    def _get_preference(self, scope: str, scope_id: str | None) -> ModelPreference | None:
        if scope != "global" and not scope_id:
            return None
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM model_preferences WHERE scope = ? AND scope_id IS ?", (scope, scope_id)).fetchone()
        return self._preference_from_row(row) if row else None

    def _validate_model_ref(self, model_ref: str) -> None:
        provider_id, _ = split_model_ref(model_ref)
        if self.providers.get(provider_id) is None:
            raise ValueError(f"Provider modèle inconnu: {provider_id}")

    def _preference_from_row(self, row) -> ModelPreference:
        return ModelPreference(row["id"], row["scope"], row["scope_id"], row["primary_model_ref"], row["fallback_model_ref"], row["created_at"], row["updated_at"])


def split_model_ref(model_ref: str) -> tuple[str, str]:
    parts = [part for part in str(model_ref or "").split("/") if part]
    if len(parts) < 2:
        raise ValueError("Référence modèle invalide. Format attendu : provider/model.")
    return parts[0], "/".join(parts[1:])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
