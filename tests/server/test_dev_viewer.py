"""The local-development viewer bypass (config.DEV_VIEWER_LOGIN): off by default, localhost only."""

from __future__ import annotations

from server.app.config import settings


async def test_viewer_requires_login_by_default(client):
    assert (await client.get("/api/me")).status_code == 401


async def test_dev_viewer_acts_as_a_stand_in_user(client, monkeypatch):
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    response = await client.get("/api/me")
    assert response.status_code == 200, response.text
    assert response.json()["login"] == "dev"


def test_dev_viewer_is_refused_on_a_public_url(monkeypatch):
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    monkeypatch.setattr(settings, "UNPACK_BASE_URL", "https://unpack.example.com")
    assert any("DEV_VIEWER_LOGIN" in p for p in settings.required_problems())
    monkeypatch.setattr(settings, "UNPACK_BASE_URL", "http://127.0.0.1:8000")
    assert not any("DEV_VIEWER_LOGIN" in p for p in settings.required_problems())


def test_public_viewer_allows_the_stand_in_user_on_a_public_url(monkeypatch):
    monkeypatch.setattr(settings, "UNPACK_BASE_URL", "https://unpack.example.com")
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    monkeypatch.setattr(settings, "PUBLIC_VIEWER", True)
    assert not any("DEV_VIEWER_LOGIN" in p or "PUBLIC_VIEWER" in p for p in settings.required_problems())

    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "")
    assert any("PUBLIC_VIEWER" in p for p in settings.required_problems())
