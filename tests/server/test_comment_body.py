"""The PR comment asks for a GitHub login only when the viewer needs one."""

from __future__ import annotations

from server.app.config import settings
from server.app.github.comments import build_comment_body


def _body() -> str:
    return build_comment_body(
        analysis_public_id="abc", short_sha="1234567", summary="Adds a helper.",
        stats={"functions_changed": 1, "by_change": {}}, not_reached=[], banner_message=None,
        image_url=None, live_url="https://unpack.example/a/abc", generated_at="2026-11-21 10:00 UTC",
    )


def test_comment_mentions_login_by_default(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_VIEWER", False)
    assert "GitHub login and repo access required" in _body()


def test_public_viewer_comment_does_not_ask_for_login(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_VIEWER", True)
    body = _body()
    assert "login" not in body.lower()
    assert "[Open the live graph →](https://unpack.example/a/abc)" in body
