from __future__ import annotations


def list_channels() -> list[dict]:
    return [
        {"id": "web", "name": "Web", "status": "active"},
        {"id": "cli", "name": "CLI", "status": "active"},
        {"id": "telegram", "name": "Telegram", "status": "stub"},
        {"id": "discord", "name": "Discord", "status": "stub"},
        {"id": "slack", "name": "Slack", "status": "stub"},
    ]
