from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from omega_agent.config import OmegaConfig
from omega_agent.connectors.connector_auth import compute_auth_status
from omega_agent.connectors.registry import ConnectorsRegistry
from omega_agent.providers.registry import ProviderRegistry
from omega_agent.registries.channels import list_channels
from omega_agent.runtime.a2a_agents import A2AAgentsRegistry
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.context import current_runtime_mode
from omega_agent.runtime.events import EventsStore
from omega_agent.runtime.mcp_servers import MCPServersRegistry
from omega_agent.runtime.plugins_registry import PluginsRegistry
from omega_agent.runtime.skills_registry import SkillsRegistry
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tools_registry import HANDLERS, list_tools
from omega_agent.security.redaction import redact

RISK_VALUES = {"low", "medium", "high", "critical"}
OWNER_VALUES = {"builtin", "local", "external", "untrusted"}


@dataclass(frozen=True)
class Capability:
    id: str
    type: str
    name: str
    description: str
    enabled: bool
    available: bool
    risk_level: str
    scopes: list[str]
    requires_auth: bool
    auth_status: str
    requires_approval_default: bool
    owner: str
    source: str
    version: str
    tags: list[str]
    input_schema: dict | None
    output_schema: dict | None
    metadata: dict
    created_at: str
    updated_at: str

    def as_api(self) -> dict:
        return redact(asdict(self))


class CapabilitiesRegistry:
    def __init__(self, config: OmegaConfig):
        self.config = config
        self.events = EventsStore(config)

    def list(
        self,
        *,
        type: str | None = None,
        risk_level: str | None = None,
        enabled: bool | None = None,
        auth_status: str | None = None,
        query: str | None = None,
        refresh: bool = True,
    ) -> list[Capability]:
        if refresh and self.config.capabilities_enabled:
            self.refresh()
        items = self._list_from_db()
        if type:
            items = [item for item in items if item.type == type]
        if risk_level:
            items = [item for item in items if item.risk_level == risk_level]
        if enabled is not None:
            items = [item for item in items if item.enabled is enabled]
        if auth_status:
            items = [item for item in items if item.auth_status == auth_status]
        if query:
            needle = query.strip().lower()
            items = [
                item
                for item in items
                if needle in item.id.lower()
                or needle in item.name.lower()
                or needle in item.description.lower()
                or any(needle in tag.lower() for tag in item.tags)
            ]
        return items

    def search(self, query: str, limit: int = 50) -> list[Capability]:
        return self.list(query=query)[:limit]

    def refresh(self) -> dict:
        capabilities = self._collect()
        self._upsert_many(capabilities)
        return {"count": len(capabilities)}

    def get(self, capability_id: str) -> Capability | None:
        if self.config.capabilities_enabled:
            self.refresh()
        with connect_runtime_db(self.config) as conn:
            row = conn.execute("SELECT * FROM capabilities WHERE id = ?", (capability_id,)).fetchone()
        return _from_row(row) if row else None

    def patch(self, capability_id: str, values: dict) -> Capability | None:
        current = self.get(capability_id)
        if current is None:
            return None
        allowed = {"enabled"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Capability fields non modifiables: {', '.join(sorted(unknown))}")
        enabled = bool(values.get("enabled", current.enabled))
        now = _now()
        with connect_runtime_db(self.config) as conn:
            conn.execute("UPDATE capabilities SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, now, capability_id))
        event_type = "capability.enabled" if enabled else "capability.disabled"
        self.events.add(event_type, {"id": capability_id})
        return self.get(capability_id)

    def enable(self, capability_id: str) -> Capability | None:
        return self.patch(capability_id, {"enabled": True})

    def disable(self, capability_id: str) -> Capability | None:
        return self.patch(capability_id, {"enabled": False})

    def _collect(self) -> list[Capability]:
        now = _now()
        capabilities: list[Capability] = []
        capabilities.extend(self._tool_capabilities(now))
        capabilities.extend(self._skill_capabilities(now))
        capabilities.extend(self._plugin_capabilities(now))
        capabilities.extend(self._provider_capabilities(now))
        capabilities.extend(self._agent_profile_capabilities(now))
        capabilities.extend(self._channel_capabilities(now))
        capabilities.extend(self._mcp_capabilities(now))
        capabilities.extend(self._a2a_capabilities(now))
        capabilities.extend(self._connector_capabilities(now))
        return capabilities

    def _tool_capabilities(self, now: str) -> list[Capability]:
        result = []
        for tool in list_tools(self.config):
            result.append(
                Capability(
                    id=f"tool:{tool.id}",
                    type="tool",
                    name=tool.name,
                    description=tool.description,
                    enabled=tool.enabled,
                    available=tool.handler in HANDLERS,
                    risk_level=_risk(tool.risk_level or tool.risk),
                    scopes=[tool.category, "workspace"],
                    requires_auth=False,
                    auth_status="none",
                    requires_approval_default=tool.requires_approval,
                    owner="builtin",
                    source="omega.tools",
                    version="builtin",
                    tags=[tool.category, "tool"],
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                    metadata={"handler": tool.handler, "category": tool.category},
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _skill_capabilities(self, now: str) -> list[Capability]:
        return [
            Capability(
                id=f"skill:{skill.id}",
                type="skill",
                name=skill.name,
                description=skill.description,
                enabled=skill.enabled,
                available=True,
                risk_level=_risk(skill.risk_level),
                scopes=["workspace"],
                requires_auth=False,
                auth_status="none",
                requires_approval_default=False,
                owner="untrusted" if (skill.metadata or {}).get("trust_level") == "untrusted" else "local",
                source=skill.path,
                version=skill.version,
                tags=list(skill.tags or []) + ["skill"],
                input_schema=None,
                output_schema=None,
                metadata={
                    "path": skill.path,
                    "allowed_tools": skill.allowed_tools or [],
                    "status": skill.status,
                    "skill_type": skill.skill_type,
                },
                created_at=now,
                updated_at=now,
            )
            for skill in SkillsRegistry(self.config).list()
        ]

    def _plugin_capabilities(self, now: str) -> list[Capability]:
        result = []
        for plugin in PluginsRegistry(self.config).list():
            owner = "untrusted" if plugin.trust_level in {"untrusted", "blocked"} else "local"
            enabled = plugin.enabled and owner != "untrusted"
            result.append(
                Capability(
                    id=f"plugin:{plugin.id}",
                    type="plugin",
                    name=plugin.name,
                    description=plugin.description,
                    enabled=enabled,
                    available=plugin.status == "loaded",
                    risk_level=_plugin_risk(plugin.trust_level),
                    scopes=["manifest"],
                    requires_auth=False,
                    auth_status="none",
                    requires_approval_default=True,
                    owner=owner,
                    source=plugin.path,
                    version=plugin.version,
                    tags=["plugin", plugin.trust_level],
                    input_schema=None,
                    output_schema=None,
                    metadata={"path": plugin.path, "status": plugin.status, "trust_level": plugin.trust_level, "declares": plugin.declares},
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _provider_capabilities(self, now: str) -> list[Capability]:
        result = []
        for provider in ProviderRegistry(self.config).list():
            info = provider.info()
            requires_auth = info.auth_type != "none"
            if current_runtime_mode() == "cli":
                auth_status = "unknown" if requires_auth else "none"
                auth_metadata = {}
            else:
                try:
                    auth = provider.check_auth()
                    auth_status = "none" if info.auth_type == "none" else auth.status
                    auth_metadata = auth.metadata
                except Exception as exc:
                    auth_status = "invalid"
                    auth_metadata = {"error": str(exc)}
            result.append(
                Capability(
                    id=f"provider:{info.id}",
                    type="provider",
                    name=info.name,
                    description=info.description,
                    enabled=info.enabled,
                    available=info.enabled,
                    risk_level="medium" if requires_auth else "low",
                    scopes=["provider", "model"],
                    requires_auth=requires_auth,
                    auth_status=auth_status,
                    requires_approval_default=False,
                    owner="builtin",
                    source="omega.providers",
                    version="builtin",
                    tags=["provider", info.id],
                    input_schema=None,
                    output_schema=None,
                    metadata={**info.as_api(), "auth": redact(auth_metadata)},
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _agent_profile_capabilities(self, now: str) -> list[Capability]:
        return [
            Capability(
                id=f"agent_profile:{profile.id}",
                type="agent_profile",
                name=profile.name,
                description=profile.description,
                enabled=profile.enabled,
                available=True,
                risk_level=_risk(profile.risk_level),
                scopes=["session"],
                requires_auth=False,
                auth_status="none",
                requires_approval_default=False,
                owner="builtin" if getattr(profile, "builtin", False) else "local",
                source="omega.agent_profiles",
                version="builtin",
                tags=["agent_profile"],
                input_schema=None,
                output_schema=None,
                metadata={"allowed_tools": profile.allowed_tools, "allowed_skills": profile.allowed_skills},
                created_at=now,
                updated_at=now,
            )
            for profile in AgentProfilesStore(self.config).list()
        ]

    def _channel_capabilities(self, now: str) -> list[Capability]:
        result = []
        for channel in list_channels():
            status = str(channel.get("status") or "unknown")
            result.append(
                Capability(
                    id=f"channel:{channel['id']}",
                    type="channel",
                    name=str(channel.get("name") or channel["id"]),
                    description=f"Canal Omega {channel.get('name') or channel['id']}",
                    enabled=status == "active",
                    available=status == "active",
                    risk_level="medium" if channel["id"] not in {"web", "cli"} else "low",
                    scopes=["channel"],
                    requires_auth=channel["id"] not in {"web", "cli"},
                    auth_status="none" if channel["id"] in {"web", "cli"} else "missing",
                    requires_approval_default=False,
                    owner="builtin",
                    source="omega.channels",
                    version="builtin",
                    tags=["channel", str(channel["id"])],
                    input_schema=None,
                    output_schema=None,
                    metadata=channel,
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _connector_capabilities(self, now: str) -> list[Capability]:
        if not getattr(self.config, "connectors_enabled", True):
            return []
        result: list[Capability] = []
        for connector in ConnectorsRegistry(self.config).list():
            auth_status = compute_auth_status(connector)
            owner = "untrusted" if connector.trust_level in {"untrusted", "blocked"} else "builtin" if connector.trust_level == "builtin" else "local"
            for operation in connector.operations:
                capability_id = f"connector:{connector.id}:{operation.id}"
                enabled = connector.enabled and operation.enabled and connector.trust_level != "blocked"
                result.append(
                    Capability(
                        id=capability_id,
                        type="connector_operation",
                        name=f"{connector.name}: {operation.name}",
                        description=operation.description or connector.description,
                        enabled=enabled,
                        available=connector.status == "available" and auth_status in {"none", "configured"},
                        risk_level=_risk(operation.risk_level),
                        scopes=list(dict.fromkeys(["connector", connector.type, *connector.scopes])),
                        requires_auth=connector.auth_type != "none",
                        auth_status=auth_status,
                        requires_approval_default=operation.requires_approval_default,
                        owner=owner,
                        source=f"omega.connectors:{connector.id}",
                        version="v1",
                        tags=["connector", connector.type, operation.action_category],
                        input_schema=operation.input_schema,
                        output_schema=operation.output_schema,
                        metadata={
                            "connector_id": connector.id,
                            "operation_id": operation.id,
                            "method": operation.method,
                            "path": operation.path,
                            "trust_level": connector.trust_level,
                            "action_category": operation.action_category,
                        },
                        created_at=now,
                        updated_at=now,
                    )
                )
        return result

    def _mcp_capabilities(self, now: str) -> list[Capability]:
        result = []
        for server in MCPServersRegistry(self.config).list():
            result.append(
                Capability(
                    id=f"mcp_server:{server.id}",
                    type="mcp_server",
                    name=server.name,
                    description=server.description,
                    enabled=server.enabled and self.config.capabilities_mcp_enabled,
                    available=False,
                    risk_level="high" if server.trust_level == "untrusted" else "medium",
                    scopes=server.scopes,
                    requires_auth=bool(server.auth_ref),
                    auth_status="configured" if server.auth_ref else "none",
                    requires_approval_default=True,
                    owner="untrusted" if server.trust_level in {"untrusted", "blocked"} else "local",
                    source=server.url or server.command or "manifest",
                    version="manifest",
                    tags=["mcp", server.trust_level],
                    input_schema=None,
                    output_schema=None,
                    metadata={**server.as_api(), "execution": "disabled_v1"},
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _a2a_capabilities(self, now: str) -> list[Capability]:
        result = []
        for agent in A2AAgentsRegistry(self.config).list():
            result.append(
                Capability(
                    id=f"a2a_agent:{agent.id}",
                    type="a2a_agent",
                    name=agent.name,
                    description=agent.description,
                    enabled=agent.enabled and self.config.capabilities_a2a_enabled,
                    available=False,
                    risk_level="high" if agent.trust_level == "untrusted" else "medium",
                    scopes=agent.scopes,
                    requires_auth=False,
                    auth_status="none",
                    requires_approval_default=True,
                    owner="untrusted" if agent.trust_level in {"untrusted", "blocked"} else "local",
                    source=agent.endpoint or "manifest",
                    version="manifest",
                    tags=["a2a", agent.trust_level],
                    input_schema=None,
                    output_schema=None,
                    metadata={**agent.as_api(), "execution": "disabled_v1"},
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def _upsert_many(self, capabilities: list[Capability]) -> None:
        existing = {item.id: item for item in self._list_from_db()}
        current_ids = {capability.id for capability in capabilities}
        pending_events: list[tuple[str, dict]] = []
        with connect_runtime_db(self.config) as conn:
            for capability in capabilities:
                previous = existing.get(capability.id)
                enabled = capability.enabled
                if previous is not None:
                    enabled = bool(previous.enabled and capability.enabled)
                if capability.owner == "untrusted" and self.config.capabilities_untrusted_disabled_by_default:
                    enabled = False
                if capability.risk_level == "critical" and not capability.requires_approval_default:
                    enabled = False
                created_at = previous.created_at if previous and previous.created_at else capability.created_at
                conn.execute(
                    """
                    INSERT INTO capabilities(
                        id, type, name, description, enabled, available, risk_level,
                        scopes_json, requires_auth, auth_status, requires_approval_default,
                        owner, source, version, tags_json, input_schema_json,
                        output_schema_json, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type=excluded.type,
                        name=excluded.name,
                        description=excluded.description,
                        enabled=excluded.enabled,
                        available=excluded.available,
                        risk_level=excluded.risk_level,
                        scopes_json=excluded.scopes_json,
                        requires_auth=excluded.requires_auth,
                        auth_status=excluded.auth_status,
                        requires_approval_default=excluded.requires_approval_default,
                        owner=excluded.owner,
                        source=excluded.source,
                        version=excluded.version,
                        tags_json=excluded.tags_json,
                        input_schema_json=excluded.input_schema_json,
                        output_schema_json=excluded.output_schema_json,
                        metadata_json=excluded.metadata_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        capability.id,
                        capability.type,
                        capability.name,
                        capability.description,
                        1 if enabled else 0,
                        1 if capability.available else 0,
                        capability.risk_level,
                        json.dumps(capability.scopes, ensure_ascii=False),
                        1 if capability.requires_auth else 0,
                        capability.auth_status,
                        1 if capability.requires_approval_default else 0,
                        _owner(capability.owner),
                        capability.source,
                        capability.version,
                        json.dumps(capability.tags, ensure_ascii=False),
                        _json_or_none(capability.input_schema),
                        _json_or_none(capability.output_schema),
                        json.dumps(redact(capability.metadata), ensure_ascii=False),
                        created_at,
                        capability.updated_at,
                    ),
                )
                if previous is None:
                    pending_events.append(("capability.created", {"id": capability.id, "type": capability.type, "name": capability.name}))
                elif previous.enabled != enabled:
                    pending_events.append(("capability.updated", {"id": capability.id, "type": capability.type, "enabled": enabled}))
            stale_ids = sorted(set(existing) - current_ids)
            for stale_id in stale_ids:
                conn.execute("DELETE FROM capabilities WHERE id = ?", (stale_id,))
                pending_events.append(("capability.updated", {"id": stale_id, "deleted": True}))
        for event_type, payload in pending_events:
            self.events.add(event_type, payload)

    def _list_from_db(self) -> list[Capability]:
        with connect_runtime_db(self.config) as conn:
            rows = conn.execute("SELECT * FROM capabilities ORDER BY type, name").fetchall()
        return [_from_row(row) for row in rows]


def _from_row(row) -> Capability:
    return Capability(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        description=row["description"],
        enabled=bool(row["enabled"]),
        available=bool(row["available"]),
        risk_level=row["risk_level"],
        scopes=json.loads(row["scopes_json"] or "[]"),
        requires_auth=bool(row["requires_auth"]),
        auth_status=row["auth_status"],
        requires_approval_default=bool(row["requires_approval_default"]),
        owner=row["owner"],
        source=row["source"],
        version=row["version"],
        tags=json.loads(row["tags_json"] or "[]"),
        input_schema=_json(row["input_schema_json"]),
        output_schema=_json(row["output_schema_json"]),
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json_or_none(value: Any) -> str | None:
    return None if value is None else json.dumps(redact(value), ensure_ascii=False)


def _json(value: str | None) -> dict | None:
    if not value:
        return None
    return json.loads(value)


def _risk(value: str) -> str:
    lowered = str(value or "medium").lower()
    return lowered if lowered in RISK_VALUES else "medium"


def _owner(value: str) -> str:
    lowered = str(value or "builtin").lower()
    return lowered if lowered in OWNER_VALUES else "untrusted"


def _plugin_risk(trust_level: str) -> str:
    if trust_level == "blocked":
        return "critical"
    if trust_level == "untrusted":
        return "high"
    if trust_level == "local":
        return "medium"
    return "low"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
