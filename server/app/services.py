"""Process-wide services: the GitHub client. Tests replace it with a mock transport."""

from __future__ import annotations

import os

from .config import settings
from .github.service import GitHubService

_github: GitHubService | None = None


def _read_private_key() -> str | None:
    path = settings.GITHUB_APP_PRIVATE_KEY_PATH
    if settings.GITHUB_APP_ID and path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return None


def get_github() -> GitHubService:
    global _github
    if _github is None:
        _github = GitHubService(settings.GITHUB_API_URL, settings.GITHUB_APP_ID, _read_private_key())
    return _github


def set_github(service: GitHubService | None) -> None:
    global _github
    _github = service


_oauth_transport = None


def set_oauth_transport(transport) -> None:
    """Tests inject a mock transport for the GitHub OAuth token exchange."""
    global _oauth_transport
    _oauth_transport = transport


def get_oauth_http():
    import httpx

    return httpx.AsyncClient(timeout=20.0, transport=_oauth_transport)
