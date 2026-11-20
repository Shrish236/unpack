"""End-to-end tests for Unpack CLI hook install/chain/push/dry-run/mock-server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from cli.config import resolve_repo_config
from cli.hook import get_hook_status, install_hook, parse_pre_push_refs, uninstall_hook
from cli.mock_server import create_mock_server

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(
        {
            "GIT_AUTHOR_NAME": "Test Dev",
            "GIT_AUTHOR_EMAIL": "dev@example.com",
            "GIT_COMMITTER_NAME": "Test Dev",
            "GIT_COMMITTER_EMAIL": "dev@example.com",
        }
    )
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=check,
    )


class TestCliEndToEnd(unittest.TestCase):
    def test_parse_pre_push_refs_skips_deletes_and_tags(self) -> None:
        stdin = "\n".join(
            [
                "refs/heads/old " + ("0" * 40) + " refs/heads/old " + ("a" * 40),
                "refs/tags/v1.0 " + ("b" * 40) + " refs/tags/v1.0 " + ("0" * 40),
                "refs/heads/feat/x " + ("c" * 40) + " refs/heads/feat/x " + ("0" * 40),
            ]
        )
        refs = parse_pre_push_refs(stdin)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][0], "refs/heads/feat/x")

    def test_hook_chaining_real_git_push_mock_server_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bare = root / "origin" / "httpx-demo.git"
            work = root / "httpx-demo"
            out_dir = root / "received"
            cfg_path = root / "unpack-config.json"
            fake_home = root / "home"
            fake_home.mkdir()
            bare.mkdir(parents=True)
            work.mkdir()

            _git(bare, "init", "--bare", "-b", "main")
            _git(work, "init", "-b", "main")
            _git(work, "remote", "add", "origin", str(bare))

            # Initial commit on main
            (work / "client.py").write_text("def send():\n    return 200\n", encoding="utf-8")
            _git(work, "add", ".")
            _git(work, "commit", "-m", "init")
            _git(work, "push", "-u", "origin", "main")

            # Add a pre-existing hook to verify chaining & restoration
            marker_file = root / "orig_hook_ran.txt"
            orig_hook = work / ".git" / "hooks" / "pre-push"
            orig_hook.write_text(
                f"#!/bin/sh\necho ran > {marker_file}\nexit 0\n",
                encoding="utf-8",
            )
            orig_hook.chmod(0o755)

            # Start local mock server on ephemeral port
            server, state = create_mock_server("127.0.0.1", 0, out_dir=out_dir, quiet=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                env = {
                    "HOME": str(fake_home),
                    "UNPACK_CONFIG_PATH": str(cfg_path),
                }

                # Create a repo .env secret + matching Gemini CLI session in fake_home
                (work / ".env").write_text("DEMO_SECRET=super_secret_demo_val\n", encoding="utf-8")
                (work / ".gitignore").write_text(".env\n", encoding="utf-8")

                # Feature branch commit containing a secret that must be redacted
                _git(work, "checkout", "-b", "feat/retries")
                (work / "client.py").write_text(
                    'def send():\n    token = "super_secret_demo_val"\n    return 201\n',
                    encoding="utf-8",
                )
                _git(work, "add", "client.py", ".gitignore")
                _git(work, "commit", "-m", "add retry logic")

                # Write matching Gemini CLI session in fake_home/.gemini
                real_work = os.path.realpath(str(work))
                gemini_dir = fake_home / ".gemini"
                gemini_dir.mkdir(parents=True)
                (gemini_dir / "projects.json").write_text(
                    json.dumps({"projects": {real_work: "httpxdemo"}}),
                    encoding="utf-8",
                )
                chats_dir = gemini_dir / "tmp" / "httpxdemo" / "chats"
                chats_dir.mkdir(parents=True)
                session_file = chats_dir / "session-2026-11-20T12-00-12345678.jsonl"
                session_lines = [
                    {
                        "sessionId": "12345678",
                        "projectHash": "httpxdemo",
                        "startTime": "2026-11-20T11:55:00Z",
                        "lastUpdated": "2099-01-01T00:00:00Z",
                    },
                    {
                        "id": "u1",
                        "type": "user",
                        "content": [{"text": "Add retries using super_secret_demo_val"}],
                    },
                    {
                        "id": "g1",
                        "type": "gemini",
                        "content": [{"text": "Updated client.py"}],
                        "tokens": {"input": 500},
                        "toolCalls": [
                            {
                                "id": "tc1",
                                "name": "replace",
                                "args": {
                                    "file_path": "client.py",
                                    "instruction": "Update return code",
                                },
                                "resultDisplay": {
                                    "fileDiff": "@@ -1,2 +1,3 @@",
                                    "fileName": "client.py",
                                    "filePath": "client.py",
                                    "originalContent": "def send():\n    return 200\n",
                                    "newContent": (
                                        'def send():\n    token = "super_secret_demo_val"\n'
                                        "    return 201\n"
                                    ),
                                },
                            }
                        ],
                    },
                ]
                session_file.write_text(
                    "\n".join(json.dumps(r) for r in session_lines) + "\n",
                    encoding="utf-8",
                )

                # Install hook via function with isolated UNPACK_CONFIG_PATH
                old_cfg_env = os.environ.get("UNPACK_CONFIG_PATH")
                os.environ["UNPACK_CONFIG_PATH"] = str(cfg_path)
                try:
                    hook_path, backup_path = install_hook(
                        work,
                        server_url=state.base_url,
                        token="unp_test_token_123456",
                        default_branch="main",
                        timeout_s=5.0,
                        python_executable=sys.executable,
                    )
                    self.assertTrue(hook_path.exists())
                    self.assertIsNotNone(backup_path)
                    self.assertTrue(backup_path.exists())

                    status = get_hook_status(work)
                    self.assertTrue(status["installed"])
                    self.assertEqual(status["chained_backup"], backup_path)

                    resolved = resolve_repo_config(work)
                    self.assertEqual(resolved.server_url, state.base_url)
                    self.assertEqual(resolved.token, "unp_test_token_123456")
                finally:
                    if old_cfg_env is None:
                        os.environ.pop("UNPACK_CONFIG_PATH", None)
                    else:
                        os.environ["UNPACK_CONFIG_PATH"] = old_cfg_env

                # Trigger REAL git push!
                push_res = _git(work, "push", "-u", "origin", "feat/retries", env=env)
                self.assertEqual(push_res.returncode, 0)
                # Original chained hook must have executed
                self.assertTrue(marker_file.exists())

                # Mock server must have received exactly 1 payload
                self.assertEqual(len(state.received), 1)
                received = state.received[0]

                # Validate contract fields
                self.assertEqual(received["schema_version"], 1)
                self.assertEqual(received["branch"], "feat/retries")
                self.assertEqual(received["repo"]["name"], "httpx-demo")
                self.assertEqual(len(received["commits"]), 1)
                self.assertEqual(received["client"]["hook"], "pre-push")
                self.assertIsNotNone(received["session"])
                self.assertEqual(received["session"]["file_name"], session_file.name)
                # tokens field must have been trimmed
                self.assertNotIn("tokens", received["session"]["lines"][2])

                # Secret must NOT appear anywhere in serialized payload
                serialized = json.dumps(received)
                self.assertNotIn("super_secret_demo_val", serialized)
                self.assertGreaterEqual(received["redactions"].get("env_value", 0), 3)

                # Validate against contract/schema/ingest_payload.json if jsonschema is installed
                try:
                    import jsonschema

                    schema = json.loads(
                        (REPO_ROOT / "contract" / "schema" / "ingest_payload.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    jsonschema.validate(instance=received, schema=schema)
                except ImportError:
                    pass

                # Tag push must be skipped (count stays 1)
                _git(work, "tag", "v0.1.0")
                _git(work, "push", "origin", "v0.1.0", env=env)
                self.assertEqual(len(state.received), 1)

                # Test CLI `push --dry-run` writes redacted payload locally
                dry_out = root / "dry.json"
                dry_proc = subprocess.run(
                    [sys.executable, "-m", "cli", "push", "--dry-run", str(dry_out)],
                    cwd=str(work),
                    env={
                        **os.environ,
                        **env,
                        "PYTHONPATH": str(REPO_ROOT),
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
                self.assertIn("Wrote dry-run payload", dry_proc.stdout)
                dry_data = json.loads(dry_out.read_text(encoding="utf-8"))
                self.assertEqual(dry_data["client"]["hook"], "manual")
                self.assertNotIn("super_secret_demo_val", json.dumps(dry_data))

                # Fail-open test: unreachable server must NOT block git push
                (work / "client.py").write_text("def send():\n    return 202\n", encoding="utf-8")
                _git(work, "add", "client.py")
                _git(work, "commit", "-m", "second commit")
                push_offline = _git(
                    work,
                    "push",
                    "origin",
                    "feat/retries",
                    env={**env, "UNPACK_SERVER": "http://127.0.0.1:9"},
                )
                self.assertEqual(push_offline.returncode, 0)
                self.assertIn("Unpack warning:", push_offline.stderr)

                # Uninstall must restore the original pre-push hook
                removed_hook, restored_backup, _ = uninstall_hook(work)
                self.assertTrue(removed_hook)
                self.assertTrue(restored_backup)
                self.assertIn("orig_hook_ran.txt", orig_hook.read_text(encoding="utf-8"))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
