from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.storage.db import connect_db


def migrate(config: OmegaConfig) -> None:
    with connect_db(config) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                active_agent TEXT NOT NULL DEFAULT 'Omega Agent',
                project_id TEXT,
                active_agent_profile_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS agent_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                system_prompt TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                allowed_tools_json TEXT NOT NULL DEFAULT '[]',
                allowed_skills_json TEXT NOT NULL DEFAULT '[]',
                risk_level TEXT NOT NULL DEFAULT 'low',
                policy_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                policy_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS project_permissions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                value_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS channels (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK(type IN ('web','cli','webhook','telegram','discord')),
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'disabled',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channel_accounts (
                id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                external_account_id TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                route_to_agent TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                schedule_type TEXT NOT NULL CHECK(schedule_type IN ('once','interval','cron')),
                schedule_value TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run_at TEXT,
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS standing_orders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT NOT NULL CHECK(scope IN ('global','project','session')),
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS delegations (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_agent_id TEXT NOT NULL,
                child_agent_id TEXT NOT NULL,
                task TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                result TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                session_id TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reasoning_events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                message_id TEXT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('pending','running','completed','failed')),
                visibility TEXT NOT NULL CHECK(visibility IN ('public','internal','redacted')),
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
                action_type TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
                kind TEXT NOT NULL,
                input_json TEXT NOT NULL DEFAULT '{}',
                output_json TEXT NOT NULL DEFAULT '{}',
                logs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('global','session','project')),
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tools_state (
                id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '0.1.0',
                risk_level TEXT NOT NULL DEFAULT 'low',
                enabled INTEGER NOT NULL DEFAULT 1,
                allowed_tools_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                path TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '0.1.0',
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 0,
                trust_level TEXT NOT NULL DEFAULT 'untrusted',
                manifest_json TEXT NOT NULL DEFAULT '{}',
                path TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                auth_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_catalog (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_ref TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                context_window INTEGER NOT NULL DEFAULT 0,
                max_output_tokens INTEGER NOT NULL DEFAULT 0,
                capabilities_json TEXT NOT NULL DEFAULT '{}',
                speed_tier TEXT NOT NULL DEFAULT 'balanced',
                cost_tier TEXT NOT NULL DEFAULT 'unknown',
                enabled INTEGER NOT NULL DEFAULT 1,
                available INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(provider_id) REFERENCES model_providers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS model_preferences (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('global','project','session','agent_profile')),
                scope_id TEXT,
                primary_model_ref TEXT NOT NULL,
                fallback_model_ref TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope, scope_id)
            );

            CREATE TABLE IF NOT EXISTS provider_auth_status (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('configured','missing','invalid','unknown')),
                auth_method TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS model_usage_events (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                provider_id TEXT NOT NULL,
                model_ref TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "status" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        if "active_agent" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN active_agent TEXT NOT NULL DEFAULT 'Omega Agent'")
        if "project_id" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT")
        if "active_agent_profile_id" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN active_agent_profile_id TEXT")
        if "metadata_json" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "metadata_json" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "session_id" not in columns:
            conn.execute("ALTER TABLE events ADD COLUMN session_id TEXT")
        if "payload_json" not in columns and "payload" in columns:
            conn.execute("ALTER TABLE events ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")
