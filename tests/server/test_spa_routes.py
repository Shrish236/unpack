"""The server serves the single-page app at /, at the home variants and at analysis pages."""

from __future__ import annotations

from server.app.routers import images


async def test_spa_is_served_at_root_home_variants_and_analysis_pages(client, tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>Unpack</title>", encoding="utf-8")
    monkeypatch.setattr(images, "web_index", lambda: index)

    for path in ("/", "/home-4", "/a/abc123"):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html")
        assert "<title>Unpack</title>" in response.text

    assert (await client.get("/home-x")).status_code == 404


async def test_spa_routes_say_when_the_ui_is_not_built(client, monkeypatch):
    monkeypatch.setattr(images, "web_index", lambda: None)
    response = await client.get("/")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"
