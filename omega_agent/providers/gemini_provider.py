from __future__ import annotations

from omega_agent.providers.google_provider import GoogleProvider


class GeminiProvider(GoogleProvider):
    id = "gemini"
    name = "Google Gemini API (legacy id)"


__all__ = ["GeminiProvider"]
