from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def builtin_workflow_templates() -> list[dict[str, Any]]:
    return deepcopy(
        [
            {
                "id": "repo-health-check",
                "name": "Repo Health Check",
                "description": "Scan the workspace, inspect git status, run a lightweight test command, and summarize the result.",
                "category": "code",
                "definition": {
                    "name": "Repo Health Check",
                    "description": "Scan repo, git status, tests, summary.",
                    "version": "1.0",
                    "inputs": {},
                    "steps": [
                        {
                            "id": "scan-tree",
                            "type": "tool",
                            "name": "Scan workspace tree",
                            "tool": "list_tree",
                            "arguments": {"relative_path": ".", "max_entries": 200},
                            "on_error": "continue",
                        },
                        {
                            "id": "git-status",
                            "type": "tool",
                            "name": "Git status",
                            "tool": "git_status",
                            "arguments": {},
                            "on_error": "continue",
                        },
                        {
                            "id": "run-tests",
                            "type": "shell",
                            "name": "Run detected default tests",
                            "command": "python -m pytest -q",
                            "timeout_seconds": 120,
                            "on_error": "continue",
                        },
                        {"id": "summary", "type": "final", "name": "Summary", "message": "Repo health check finished."},
                    ],
                },
                "metadata": {"builtin": True},
            },
            {
                "id": "frontend-build-check",
                "name": "Frontend Build Check",
                "description": "Check a frontend workspace with npm install and npm run build.",
                "category": "code",
                "definition": {
                    "name": "Frontend Build Check",
                    "description": "Install frontend dependencies when present and run build.",
                    "version": "1.0",
                    "steps": [
                        {
                            "id": "package-json",
                            "type": "tool",
                            "name": "Check package.json",
                            "tool": "file_exists",
                            "arguments": {"relative_path": "package.json"},
                            "on_error": "continue",
                        },
                        {
                            "id": "npm-install",
                            "type": "shell",
                            "name": "NPM install",
                            "command": "npm install",
                            "timeout_seconds": 300,
                            "on_error": "continue",
                        },
                        {
                            "id": "npm-build",
                            "type": "shell",
                            "name": "NPM build",
                            "command": "npm run build",
                            "timeout_seconds": 300,
                            "on_error": "continue",
                        },
                        {"id": "summary", "type": "final", "name": "Summary", "message": "Frontend build check finished."},
                    ],
                },
                "metadata": {"builtin": True},
            },
            {
                "id": "python-test-check",
                "name": "Python Test Check",
                "description": "Run pytest in the workspace and summarize failures.",
                "category": "code",
                "definition": {
                    "name": "Python Test Check",
                    "description": "Run pytest.",
                    "version": "1.0",
                    "steps": [
                        {
                            "id": "pytest",
                            "type": "shell",
                            "name": "Run pytest",
                            "command": "python -m pytest -q",
                            "timeout_seconds": 180,
                            "on_error": "continue",
                        },
                        {"id": "summary", "type": "final", "name": "Summary", "message": "Python test check finished."},
                    ],
                },
                "metadata": {"builtin": True},
            },
            {
                "id": "workspace-cleanup-plan",
                "name": "Workspace Cleanup Plan",
                "description": "Inspect workspace contents and pause for approval before any cleanup execution.",
                "category": "maintenance",
                "definition": {
                    "name": "Workspace Cleanup Plan",
                    "description": "List workspace and request approval before cleanup.",
                    "version": "1.0",
                    "steps": [
                        {
                            "id": "scan-tree",
                            "type": "tool",
                            "name": "Scan workspace tree",
                            "tool": "list_tree",
                            "arguments": {"relative_path": ".", "max_entries": 300},
                            "on_error": "continue",
                        },
                        {
                            "id": "approval",
                            "type": "approval",
                            "name": "Approve cleanup plan",
                            "message": "Review the workspace cleanup plan before any destructive action.",
                            "required": True,
                        },
                        {"id": "summary", "type": "final", "name": "Summary", "message": "Cleanup plan approved."},
                    ],
                },
                "metadata": {"builtin": True},
            },
            {
                "id": "code-fix-loop",
                "name": "Code Fix Loop",
                "description": "Run tests, inspect diff, and produce a durable summary for a future patch plan.",
                "category": "code",
                "definition": {
                    "name": "Code Fix Loop",
                    "description": "Run tests and inspect diff before a patch loop.",
                    "version": "1.0",
                    "steps": [
                        {
                            "id": "run-tests",
                            "type": "shell",
                            "name": "Run tests",
                            "command": "python -m pytest -q",
                            "timeout_seconds": 180,
                            "on_error": "continue",
                        },
                        {
                            "id": "git-diff",
                            "type": "tool",
                            "name": "Show diff",
                            "tool": "git_diff",
                            "arguments": {},
                            "on_error": "continue",
                        },
                        {"id": "summary", "type": "final", "name": "Summary", "message": "Code fix loop inspection finished."},
                    ],
                },
                "metadata": {"builtin": True},
            },
        ]
    )


def template_created_at() -> str:
    return datetime.now(timezone.utc).isoformat()
