from __future__ import annotations

from omega_agent.config import OmegaConfig
from omega_agent.storage.db import connect_db

SCHEMA_VERSION = "2026-06-22-cli-bootstrap-v1"


def migrate(config: OmegaConfig) -> None:
    with connect_db(config) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS omega_schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT value FROM omega_schema_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is not None and row["value"] == SCHEMA_VERSION:
            return
        conn.executescript(
            """
            BEGIN;

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

            CREATE TABLE IF NOT EXISTS events_v2 (
                id TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT,
                run_id TEXT,
                step_id TEXT,
                user_id TEXT,
                source TEXT NOT NULL,
                level TEXT NOT NULL,
                visibility TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
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

            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('global','project','session','agent','run')),
                scope_id TEXT,
                project_id TEXT,
                session_id TEXT,
                run_id TEXT,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                summary TEXT,
                type TEXT NOT NULL CHECK(type IN ('fact','preference','decision','procedure','warning','entity','project_note','tool_observation')),
                confidence REAL NOT NULL DEFAULT 0.8,
                importance INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL CHECK(status IN ('active','archived','deleted')) DEFAULT 'active',
                tags_json TEXT NOT NULL DEFAULT '[]',
                provenance_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL CHECK(created_by IN ('user','omega','tool','import')) DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS memory_provenance (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('user_message','assistant_message','run','tool','file','manual','imported')),
                source_id TEXT,
                source_label TEXT,
                quote TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(memory_id) REFERENCES memory_entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memory_conflicts (
                id TEXT PRIMARY KEY,
                memory_a_id TEXT NOT NULL,
                memory_b_id TEXT NOT NULL,
                conflict_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open','resolved','ignored')) DEFAULT 'open',
                resolution TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(memory_a_id) REFERENCES memory_entries(id) ON DELETE CASCADE,
                FOREIGN KEY(memory_b_id) REFERENCES memory_entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memory_suggestions (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                project_id TEXT,
                suggested_type TEXT NOT NULL,
                content TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected')) DEFAULT 'pending',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS skill_candidates (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_run_ids_json TEXT NOT NULL DEFAULT '[]',
                source_workflow_ids_json TEXT,
                detected_pattern_json TEXT NOT NULL DEFAULT '{}',
                proposed_skill_json TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL CHECK(status IN ('pending','accepted','rejected','promoted','archived')) DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS skill_versions (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL,
                definition_json TEXT NOT NULL DEFAULT '{}',
                changelog TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                UNIQUE(skill_id, version)
            );

            CREATE TABLE IF NOT EXISTS skill_test_runs (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('passed','failed','error')),
                results_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS skill_usage_events (
                id TEXT PRIMARY KEY,
                skill_id TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL,
                success INTEGER,
                duration_ms INTEGER,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(skill_id) REFERENCES skills(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS budget_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                scope_type TEXT NOT NULL CHECK(scope_type IN ('global','project','session','agent_profile','workflow')) DEFAULT 'global',
                scope_id TEXT,
                limits_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS budget_usage (
                id TEXT PRIMARY KEY,
                profile_id TEXT,
                run_id TEXT,
                workflow_run_id TEXT,
                session_id TEXT,
                project_id TEXT,
                metric TEXT NOT NULL,
                used_value REAL NOT NULL DEFAULT 0,
                limit_value REAL,
                status TEXT NOT NULL CHECK(status IN ('ok','warning','exceeded')) DEFAULT 'ok',
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(profile_id) REFERENCES budget_profiles(id) ON DELETE SET NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS budget_violations (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                workflow_run_id TEXT,
                profile_id TEXT,
                metric TEXT NOT NULL,
                used_value REAL NOT NULL,
                limit_value REAL NOT NULL,
                action_taken TEXT NOT NULL CHECK(action_taken IN ('warned','paused','denied','cancelled','approval_required')),
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES budget_profiles(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shadow_runs (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL CHECK(source_type IN ('action','run','workflow','manual_plan')),
                source_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','promoted','rejected','expired')) DEFAULT 'pending',
                objective TEXT NOT NULL,
                plan_json TEXT NOT NULL DEFAULT '{}',
                risk_report_json TEXT,
                predicted_diff_json TEXT,
                estimated_cost_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS shadow_steps (
                id TEXT PRIMARY KEY,
                shadow_run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','skipped')) DEFAULT 'pending',
                input_json TEXT,
                output_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(shadow_run_id) REFERENCES shadow_runs(id) ON DELETE CASCADE,
                UNIQUE(shadow_run_id, step_index)
            );

            CREATE TABLE IF NOT EXISTS shadow_promotions (
                id TEXT PRIMARY KEY,
                shadow_run_id TEXT NOT NULL,
                live_run_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','running','succeeded','failed','rejected')) DEFAULT 'pending',
                approved_by TEXT,
                approved_at TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(shadow_run_id) REFERENCES shadow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(live_run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS shadow_live_comparisons (
                id TEXT PRIMARY KEY,
                shadow_run_id TEXT NOT NULL,
                live_run_id TEXT NOT NULL,
                comparison_json TEXT NOT NULL DEFAULT '{}',
                success_match INTEGER,
                diff_match_score REAL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(shadow_run_id) REFERENCES shadow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(live_run_id) REFERENCES runs(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','paused','succeeded','failed','cancelled','needs_approval')),
                user_message_id TEXT,
                assistant_message_id TEXT,
                active_agent_profile_id TEXT,
                project_id TEXT,
                model_ref TEXT,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS run_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('reasoning','tool_call','approval','observation','checkpoint','rollback','final_response','error','provider_call')),
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','skipped')),
                title TEXT NOT NULL,
                input_json TEXT,
                output_json TEXT,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                UNIQUE(run_id, step_index)
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT,
                label TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES run_steps(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS action_journal (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT,
                action_type TEXT NOT NULL,
                tool_name TEXT,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                policy_decision_json TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL DEFAULT 'low',
                status TEXT NOT NULL CHECK(status IN ('planned','allowed','denied','approval_required','running','succeeded','failed','rolled_back')),
                observation_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                rollback_available INTEGER NOT NULL DEFAULT 0,
                snapshot_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(step_id) REFERENCES run_steps(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS file_snapshots (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                action_id TEXT,
                workspace_path TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                snapshot_path TEXT,
                existed_before INTEGER NOT NULL DEFAULT 0,
                content_hash_before TEXT,
                content_hash_after TEXT,
                size_before INTEGER,
                size_after INTEGER,
                created_at TEXT NOT NULL,
                restored_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(action_id) REFERENCES action_journal(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS rollback_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                snapshot_id TEXT,
                action_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY(snapshot_id) REFERENCES file_snapshots(id) ON DELETE SET NULL,
                FOREIGN KEY(action_id) REFERENCES action_journal(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS dead_letter_runs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS repo_profiles (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                workspace_path TEXT NOT NULL,
                is_git_repo INTEGER NOT NULL DEFAULT 0,
                languages_json TEXT NOT NULL DEFAULT '[]',
                frameworks_json TEXT NOT NULL DEFAULT '[]',
                package_managers_json TEXT NOT NULL DEFAULT '[]',
                test_commands_json TEXT NOT NULL DEFAULT '[]',
                build_commands_json TEXT NOT NULL DEFAULT '[]',
                entrypoints_json TEXT NOT NULL DEFAULT '[]',
                config_files_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS test_runs (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                project_id TEXT,
                command TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('running','passed','failed','error')),
                exit_code INTEGER,
                stdout TEXT NOT NULL DEFAULT '',
                stderr TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS patch_plans (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                project_id TEXT,
                title TEXT NOT NULL,
                problem TEXT NOT NULL DEFAULT '',
                proposed_changes_json TEXT NOT NULL DEFAULT '[]',
                files_to_modify_json TEXT NOT NULL DEFAULT '[]',
                risk_level TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL CHECK(status IN ('proposed','applied','verified','failed','rejected')) DEFAULT 'proposed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                session_id TEXT,
                run_id TEXT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                alternatives_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL CHECK(status IN ('active','superseded','archived')) DEFAULT 'active',
                created_by TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                provenance_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS capabilities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                available INTEGER NOT NULL DEFAULT 1,
                risk_level TEXT NOT NULL DEFAULT 'low',
                scopes_json TEXT NOT NULL DEFAULT '[]',
                requires_auth INTEGER NOT NULL DEFAULT 0,
                auth_status TEXT NOT NULL DEFAULT 'none',
                requires_approval_default INTEGER NOT NULL DEFAULT 0,
                owner TEXT NOT NULL DEFAULT 'builtin',
                source TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                input_schema_json TEXT,
                output_schema_json TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capability_usage_events (
                id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                run_id TEXT,
                session_id TEXT,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                command TEXT,
                url TEXT,
                enabled INTEGER NOT NULL DEFAULT 0,
                trust_level TEXT NOT NULL DEFAULT 'untrusted',
                scopes_json TEXT NOT NULL DEFAULT '[]',
                auth_ref TEXT,
                status TEXT NOT NULL DEFAULT 'manifest_only',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS a2a_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                endpoint TEXT,
                agent_card_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 0,
                trust_level TEXT NOT NULL DEFAULT 'untrusted',
                scopes_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'manifest_only',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','cancelled')) DEFAULT 'pending',
                dataset_name TEXT,
                started_at TEXT,
                completed_at TEXT,
                summary_json TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS eval_cases (
                id TEXT PRIMARY KEY,
                eval_run_id TEXT NOT NULL,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                expected_outcome TEXT,
                project_id TEXT,
                agent_profile_id TEXT,
                model_ref TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','running','passed','failed','error','skipped')) DEFAULT 'pending',
                score REAL,
                started_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(eval_run_id) REFERENCES eval_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_outcomes (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                session_id TEXT,
                project_id TEXT,
                success INTEGER,
                outcome TEXT NOT NULL CHECK(outcome IN ('success','partial','failed','blocked','cancelled','unknown')) DEFAULT 'unknown',
                user_feedback TEXT,
                auto_score REAL,
                human_score REAL,
                reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS run_metrics (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                total_duration_ms INTEGER NOT NULL DEFAULT 0,
                first_event_ms INTEGER,
                first_token_ms INTEGER,
                tool_calls_count INTEGER NOT NULL DEFAULT 0,
                failed_tool_calls_count INTEGER NOT NULL DEFAULT 0,
                approvals_count INTEGER NOT NULL DEFAULT 0,
                rollbacks_count INTEGER NOT NULL DEFAULT 0,
                files_changed_count INTEGER NOT NULL DEFAULT 0,
                shell_commands_count INTEGER NOT NULL DEFAULT 0,
                model_ref TEXT,
                agent_profile_id TEXT,
                estimated_cost REAL,
                risk_max TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS failure_clusters (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                failure_type TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                examples_json TEXT NOT NULL DEFAULT '[]',
                suggested_fix TEXT,
                status TEXT NOT NULL CHECK(status IN ('open','investigating','fixed','ignored')) DEFAULT 'open',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS policy_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 0,
                scope_type TEXT NOT NULL CHECK(scope_type IN ('global','project','session','agent_profile')) DEFAULT 'global',
                scope_id TEXT,
                default_action TEXT NOT NULL CHECK(default_action IN ('allow','deny','require_approval')) DEFAULT 'require_approval',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS policy_rules (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 0,
                effect TEXT NOT NULL CHECK(effect IN ('allow','deny','require_approval')),
                action_type TEXT,
                tool_name TEXT,
                resource_pattern TEXT,
                risk_level_min TEXT,
                conditions_json TEXT NOT NULL DEFAULT '{}',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(profile_id) REFERENCES policy_profiles(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS policy_simulations (
                id TEXT PRIMARY KEY,
                input_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '1.0',
                enabled INTEGER NOT NULL DEFAULT 1,
                definition_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('pending','running','paused','succeeded','failed','cancelled')) DEFAULT 'pending',
                input_json TEXT NOT NULL DEFAULT '{}',
                output_json TEXT,
                current_step_index INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS workflow_step_runs (
                id TEXT PRIMARY KEY,
                workflow_run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','skipped','waiting_approval')) DEFAULT 'pending',
                input_json TEXT,
                output_json TEXT,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workflow_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                definition_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS connectors (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK(type IN ('builtin','openapi','local_http','mcp','github','filesystem','custom')),
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 0,
                trust_level TEXT NOT NULL CHECK(trust_level IN ('builtin','local','untrusted','blocked')) DEFAULT 'untrusted',
                auth_type TEXT NOT NULL CHECK(auth_type IN ('none','env_secret','oauth_stub','token_stub')) DEFAULT 'none',
                auth_ref TEXT,
                base_url TEXT,
                scopes_json TEXT NOT NULL DEFAULT '[]',
                operations_json TEXT NOT NULL DEFAULT '[]',
                risk_level TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL CHECK(status IN ('available','missing_auth','disabled','error','unknown')) DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS connector_operations (
                id TEXT NOT NULL,
                connector_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                method TEXT,
                path TEXT,
                input_schema_json TEXT NOT NULL DEFAULT '{}',
                output_schema_json TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL DEFAULT 'low',
                requires_approval_default INTEGER NOT NULL DEFAULT 0,
                action_category TEXT NOT NULL CHECK(action_category IN ('read_only','reversible_write','destructive_write','external_side_effect','system_sensitive')) DEFAULT 'read_only',
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(id, connector_id),
                FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS connector_usage_events (
                id TEXT PRIMARY KEY,
                connector_id TEXT NOT NULL,
                operation_id TEXT,
                run_id TEXT,
                session_id TEXT,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                error TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE CASCADE,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS connector_auth_status (
                id TEXT PRIMARY KEY,
                connector_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('configured','missing','invalid','none','unknown')),
                auth_type TEXT NOT NULL DEFAULT 'none',
                auth_ref TEXT,
                last_checked_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_runs (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                run_id TEXT,
                title TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','planning','collecting','analyzing','reporting','succeeded','failed','cancelled')) DEFAULT 'pending',
                plan_json TEXT NOT NULL DEFAULT '{}',
                report_markdown TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS research_sources (
                id TEXT PRIMARY KEY,
                research_run_id TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('file','memory','connector','web','manual')),
                title TEXT NOT NULL,
                uri TEXT,
                locator TEXT,
                content_excerpt TEXT,
                trust_level TEXT NOT NULL CHECK(trust_level IN ('trusted','local','external','untrusted')) DEFAULT 'untrusted',
                collected_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(research_run_id) REFERENCES research_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_claims (
                id TEXT PRIMARY KEY,
                research_run_id TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL CHECK(status IN ('supported','weak','contradicted','unsupported','unknown')) DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(research_run_id) REFERENCES research_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_evidence (
                id TEXT PRIMARY KEY,
                research_run_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                quote TEXT,
                relevance_score REAL NOT NULL DEFAULT 0,
                supports INTEGER,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(research_run_id) REFERENCES research_runs(id) ON DELETE CASCADE,
                FOREIGN KEY(claim_id) REFERENCES research_claims(id) ON DELETE CASCADE,
                FOREIGN KEY(source_id) REFERENCES research_sources(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_reports (
                id TEXT PRIMARY KEY,
                research_run_id TEXT NOT NULL,
                format TEXT NOT NULL CHECK(format IN ('markdown','json')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(research_run_id) REFERENCES research_runs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_runs_session_updated ON runs(session_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_runs_status_updated ON runs(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_run_steps_run_index ON run_steps(run_id, step_index);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_run_created ON checkpoints(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_action_journal_run_created ON action_journal(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_file_snapshots_run_created ON file_snapshots(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_rollback_events_run_created ON rollback_events(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_memory_entries_scope_status ON memory_entries(scope, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_memory_entries_project_status ON memory_entries(project_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_memory_entries_session_status ON memory_entries(session_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_memory_provenance_memory ON memory_provenance(memory_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_memory_suggestions_status ON memory_suggestions(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_memory_conflicts_status ON memory_conflicts(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_decisions_project_status ON decisions(project_id, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_repo_profiles_workspace_updated ON repo_profiles(workspace_path, updated_at);
            CREATE INDEX IF NOT EXISTS idx_test_runs_project_started ON test_runs(project_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_test_runs_status_started ON test_runs(status, started_at);
            CREATE INDEX IF NOT EXISTS idx_patch_plans_project_updated ON patch_plans(project_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_patch_plans_status_updated ON patch_plans(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_capability_usage_capability_created ON capability_usage_events(capability_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled, updated_at);
            CREATE INDEX IF NOT EXISTS idx_a2a_agents_enabled ON a2a_agents(enabled, updated_at);
            CREATE INDEX IF NOT EXISTS idx_eval_runs_status_created ON eval_runs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_eval_cases_run_status ON eval_cases(eval_run_id, status);
            CREATE INDEX IF NOT EXISTS idx_task_outcomes_run_updated ON task_outcomes(run_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_task_outcomes_outcome_updated ON task_outcomes(outcome, updated_at);
            CREATE INDEX IF NOT EXISTS idx_run_metrics_created ON run_metrics(created_at);
            CREATE INDEX IF NOT EXISTS idx_failure_clusters_status_seen ON failure_clusters(status, last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_policy_profiles_scope_priority ON policy_profiles(scope_type, scope_id, enabled, priority);
            CREATE INDEX IF NOT EXISTS idx_policy_rules_profile_priority ON policy_rules(profile_id, enabled, priority);
            CREATE INDEX IF NOT EXISTS idx_policy_simulations_created ON policy_simulations(created_at);
            CREATE INDEX IF NOT EXISTS idx_workflows_enabled_updated ON workflows(enabled, updated_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_updated ON workflow_runs(workflow_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_updated ON workflow_runs(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_run_index ON workflow_step_runs(workflow_run_id, step_index);
            CREATE INDEX IF NOT EXISTS idx_workflow_templates_category_name ON workflow_templates(category, name);
            CREATE INDEX IF NOT EXISTS idx_connectors_type_enabled ON connectors(type, enabled, updated_at);
            CREATE INDEX IF NOT EXISTS idx_connectors_status_enabled ON connectors(status, enabled, updated_at);
            CREATE INDEX IF NOT EXISTS idx_connector_operations_connector ON connector_operations(connector_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_connector_usage_connector_created ON connector_usage_events(connector_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_connector_usage_run_created ON connector_usage_events(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_v2_timestamp ON events_v2(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_v2_type_timestamp ON events_v2(type, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_v2_session_timestamp ON events_v2(session_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_v2_run_timestamp ON events_v2(run_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_research_runs_status_updated ON research_runs(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_research_runs_session_updated ON research_runs(session_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_research_sources_run_collected ON research_sources(research_run_id, collected_at);
            CREATE INDEX IF NOT EXISTS idx_research_claims_run_status ON research_claims(research_run_id, status);
            CREATE INDEX IF NOT EXISTS idx_research_evidence_claim ON research_evidence(claim_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_research_evidence_source ON research_evidence(source_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_research_reports_run_created ON research_reports(research_run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_skill_candidates_status_updated ON skill_candidates(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_skill_versions_skill_created ON skill_versions(skill_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_skill_test_runs_skill_created ON skill_test_runs(skill_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_skill_usage_skill_created ON skill_usage_events(skill_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_budget_profiles_scope ON budget_profiles(scope_type, scope_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_budget_usage_run_metric ON budget_usage(run_id, metric, updated_at);
            CREATE INDEX IF NOT EXISTS idx_budget_usage_workflow_metric ON budget_usage(workflow_run_id, metric, updated_at);
            CREATE INDEX IF NOT EXISTS idx_budget_violations_run_created ON budget_violations(run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_budget_violations_workflow_created ON budget_violations(workflow_run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_shadow_runs_status_created ON shadow_runs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_shadow_runs_source ON shadow_runs(source_type, source_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_shadow_steps_run_index ON shadow_steps(shadow_run_id, step_index);
            CREATE INDEX IF NOT EXISTS idx_shadow_promotions_run_created ON shadow_promotions(shadow_run_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_shadow_comparisons_run_created ON shadow_live_comparisons(shadow_run_id, created_at);

            COMMIT;
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

        _add_column_if_missing(conn, "approvals", "action_id", "TEXT")

        _add_column_if_missing(conn, "memories", "project_id", "TEXT")
        _add_column_if_missing(conn, "memories", "run_id", "TEXT")
        _add_column_if_missing(conn, "memories", "source_type", "TEXT NOT NULL DEFAULT 'user'")
        _add_column_if_missing(conn, "memories", "provenance_json", "TEXT NOT NULL DEFAULT '{}'")
        _add_column_if_missing(conn, "memories", "confidence", "REAL NOT NULL DEFAULT 1.0")
        _add_column_if_missing(conn, "memories", "created_by_agent", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "decisions", "session_id", "TEXT")
        _add_column_if_missing(conn, "decisions", "alternatives_json", "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(conn, "decisions", "status", "TEXT NOT NULL DEFAULT 'active'")
        _add_column_if_missing(conn, "decisions", "created_by", "TEXT NOT NULL DEFAULT 'user'")
        _add_column_if_missing(conn, "decisions", "updated_at", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "decisions", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
        _add_column_if_missing(conn, "skills", "slug", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "skills", "status", "TEXT NOT NULL DEFAULT 'active'")
        _add_column_if_missing(conn, "skills", "skill_type", "TEXT NOT NULL DEFAULT 'prompt'")
        _add_column_if_missing(conn, "skills", "definition_json", "TEXT NOT NULL DEFAULT '{}'")
        _add_column_if_missing(conn, "skills", "test_cases_json", "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(conn, "skills", "source_candidate_id", "TEXT")
        _add_column_if_missing(conn, "skills", "created_at", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "skills", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
        _add_column_if_missing(conn, "action_journal", "budget_decision_json", "TEXT NOT NULL DEFAULT '{}'")
        _add_column_if_missing(conn, "run_metrics", "budget_violations_count", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "run_metrics", "budget_efficiency", "REAL")
        conn.execute("UPDATE skills SET slug = lower(replace(name, ' ', '-')) WHERE slug = '' OR slug IS NULL")
        conn.execute("UPDATE skills SET status = CASE WHEN enabled = 1 THEN 'active' ELSE 'disabled' END WHERE status = '' OR status IS NULL")
        conn.execute("UPDATE skills SET created_at = updated_at WHERE created_at = '' OR created_at IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_status_updated ON skills(status, updated_at)")
        conn.execute("UPDATE decisions SET updated_at = created_at WHERE updated_at = '' OR updated_at IS NULL")
        _ensure_capabilities_schema(conn)
        conn.execute(
            """
            INSERT INTO omega_schema_metadata(key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION,),
        )


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_capabilities_schema(conn) -> None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'capabilities'").fetchone()
    if row and "CHECK(type IN" in (row["sql"] or ""):
        conn.execute("ALTER TABLE capabilities RENAME TO capabilities_legacy")
        conn.executescript(
            """
            CREATE TABLE capabilities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                available INTEGER NOT NULL DEFAULT 1,
                risk_level TEXT NOT NULL DEFAULT 'low',
                scopes_json TEXT NOT NULL DEFAULT '[]',
                requires_auth INTEGER NOT NULL DEFAULT 0,
                auth_status TEXT NOT NULL DEFAULT 'none',
                requires_approval_default INTEGER NOT NULL DEFAULT 0,
                owner TEXT NOT NULL DEFAULT 'builtin',
                source TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                input_schema_json TEXT,
                output_schema_json TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            """
        )
        legacy_columns = {item["name"] for item in conn.execute("PRAGMA table_info(capabilities_legacy)").fetchall()}
        select_parts = []
        for column, default in [
            ("id", "''"),
            ("type", "'tool'"),
            ("name", "''"),
            ("description", "''"),
            ("enabled", "1"),
            ("risk_level", "'low'"),
            ("scopes_json", "'[]'"),
            ("requires_auth", "0"),
            ("requires_approval_default", "0"),
            ("owner", "'builtin'"),
            ("metadata_json", "'{}'"),
            ("updated_at", "datetime('now')"),
        ]:
            select_parts.append(column if column in legacy_columns else f"{default} AS {column}")
        conn.execute(
            f"""
            INSERT OR IGNORE INTO capabilities(
                id, type, name, description, enabled, risk_level, scopes_json,
                requires_auth, requires_approval_default, owner, metadata_json, updated_at
            )
            SELECT {', '.join(select_parts)} FROM capabilities_legacy
            """
        )
        conn.execute("DROP TABLE capabilities_legacy")
    _add_column_if_missing(conn, "capabilities", "available", "INTEGER NOT NULL DEFAULT 1")
    _add_column_if_missing(conn, "capabilities", "auth_status", "TEXT NOT NULL DEFAULT 'none'")
    _add_column_if_missing(conn, "capabilities", "source", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "capabilities", "version", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "capabilities", "tags_json", "TEXT NOT NULL DEFAULT '[]'")
    _add_column_if_missing(conn, "capabilities", "input_schema_json", "TEXT")
    _add_column_if_missing(conn, "capabilities", "output_schema_json", "TEXT")
    _add_column_if_missing(conn, "capabilities", "created_at", "TEXT NOT NULL DEFAULT ''")
