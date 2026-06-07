from __future__ import annotations


def list_providers() -> list[dict]:
    return [
        {"id": "codex", "name": "Codex OAuth", "default_model": "gpt-5.5"},
        {"id": "openai", "name": "OpenAI Agents SDK", "default_model": "gpt-5.1"},
        {"id": "mock", "name": "Mock Provider", "default_model": "mock-local"},
    ]
