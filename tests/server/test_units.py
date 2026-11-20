"""Unit tests: configuration, security helpers, diff parsing and the payload source."""

from __future__ import annotations

import time

from server.app import security
from server.app.config import Settings
from server.app.pipeline.payload import PayloadSource, build_overlay, parse_diff_hunks
from unpack_graph.source import FsSource


def test_missing_secrets_are_reported():
    s = Settings(UNPACK_BASE_URL="", DATABASE_URL="", SESSION_SECRET="short", RENDER_TOKEN_SECRET="",
                 ADMIN_TOKEN="", TOKEN_ENCRYPTION_KEY="")
    problems = s.required_problems()
    assert any("UNPACK_BASE_URL" in p for p in problems)
    assert any("DATABASE_URL" in p for p in problems)
    assert any("SESSION_SECRET must be at least 32" in p for p in problems)
    assert any("RENDER_TOKEN_SECRET is not set" in p for p in problems)
    assert any("ADMIN_TOKEN is not set" in p for p in problems)
    assert any("TOKEN_ENCRYPTION_KEY is not set" in p for p in problems)


def test_valid_settings_have_no_problems():
    from cryptography.fernet import Fernet

    s = Settings(UNPACK_BASE_URL="https://x", DATABASE_URL="postgresql://a", SESSION_SECRET="a" * 40,
                 RENDER_TOKEN_SECRET="b" * 40, ADMIN_TOKEN="c" * 40,
                 TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    assert s.required_problems() == []


def test_bad_fernet_key_is_reported():
    s = Settings(UNPACK_BASE_URL="https://x", DATABASE_URL="postgresql://a", SESSION_SECRET="a" * 40,
                 RENDER_TOKEN_SECRET="b" * 40, ADMIN_TOKEN="c" * 40, TOKEN_ENCRYPTION_KEY="not-a-key")
    assert "TOKEN_ENCRYPTION_KEY is not a valid Fernet key" in s.required_problems()


def test_ingest_token_format_and_hash():
    token = security.new_ingest_token()
    assert token.startswith("unp_")
    assert len(token) == 4 + 43
    assert security.hash_token(token) == security.hash_token(token)
    assert len(security.hash_token(token)) == 64


def test_public_id_is_22_url_safe_characters():
    pid = security.new_public_id()
    assert len(pid) == 22
    assert all(c.isalnum() or c in "-_" for c in pid)


def test_render_token_round_trip_and_expiry():
    now = time.time()
    token = security.render_token("abc123", ttl_seconds=60, now=now)
    assert security.verify_render_token("abc123", token, now=now + 1)
    assert not security.verify_render_token("other", token, now=now + 1)
    assert not security.verify_render_token("abc123", token, now=now + 120)
    assert not security.verify_render_token("abc123", None)


def test_token_encryption_round_trip():
    value = "gho_example_value"
    assert security.decrypt_secret(security.encrypt_secret(value)) == value


DIFF = """diff --git a/x.py b/x.py
index 1..2 100644
--- a/x.py
+++ b/x.py
@@ -1,3 +1,4 @@
 a
--- gone
+++ new
+b
 c
@@ -20,2 +21,2 @@
-old
+new
 end
diff --git a/y.py b/y.py
new file mode 100644
--- /dev/null
+++ b/y.py
@@ -0,0 +1,2 @@
+one
+two
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-bye
"""


def test_diff_hunks_keep_content_lines_that_look_like_headers():
    hunks = parse_diff_hunks(DIFF)
    assert [(h.new_start, h.new_end) for h in hunks["x.py"]] == [(1, 4), (21, 22)]
    assert [(h.new_start, h.new_end) for h in hunks["y.py"]] == [(1, 2)]
    assert "gone.py" in hunks
    assert hunks["gone.py"][0].new_start == 0


def test_overlay_handles_deletes_and_renames():
    files = [
        {"path": "a.py", "old_path": None, "status": "M", "is_binary": False, "head_content": "x = 1\n"},
        {"path": "new.py", "old_path": "old.py", "status": "R", "is_binary": False, "head_content": "y = 2\n"},
        {"path": "gone.py", "old_path": None, "status": "D", "is_binary": False, "head_content": None},
        {"path": "README.md", "old_path": None, "status": "M", "is_binary": False, "head_content": "hi"},
    ]
    overlay, removed = build_overlay(files)
    assert set(overlay) == {"a.py", "new.py"}
    assert removed == {"gone.py", "old.py"}


def test_payload_source_overlays_and_removes(tmp_path):
    repo = tmp_path / "src"
    repo.mkdir()
    (repo / "keep.py").write_text("def keep():\n    return 1\n")
    (repo / "drop.py").write_text("def drop():\n    return 2\n")
    base = FsSource(repo)
    source = PayloadSource(base, {"keep.py": b"def keep():\n    return 3\n", "added.py": b"x = 1\n"}, {"drop.py"})
    assert source.list_files() == ["added.py", "keep.py"]
    assert source.read("keep.py") == b"def keep():\n    return 3\n"
    assert source.read("added.py") == b"x = 1\n"
