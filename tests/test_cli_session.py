"""Tests for cli.session_finder."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cli.session_finder import (
    find_gemini_session,
    get_session_last_updated,
    load_and_trim_session,
    resolve_gemini_project_ids,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


class TestSessionFinder(unittest.TestCase):
    def test_projects_json_and_timestamp_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "my-repo"
            repo.mkdir()
            gemini_dir = root / ".gemini"
            gemini_dir.mkdir()

            real_repo = os.path.realpath(str(repo))
            (gemini_dir / "projects.json").write_text(
                json.dumps({"projects": {real_repo: "myrepo"}}),
                encoding="utf-8",
            )

            chats = gemini_dir / "tmp" / "myrepo" / "chats"
            old_sess = chats / "session-2026-11-10T10-00-aaaa1111.jsonl"
            new_sess = chats / "session-2026-11-20T10-00-bbbb2222.jsonl"

            _write_jsonl(
                old_sess,
                [
                    {
                        "sessionId": "aaaa1111",
                        "projectHash": "myrepo",
                        "startTime": "2026-11-10T10:00:00Z",
                        "lastUpdated": "2026-11-10T10:05:00Z",
                    }
                ],
            )
            _write_jsonl(
                new_sess,
                [
                    {
                        "sessionId": "bbbb2222",
                        "projectHash": "myrepo",
                        "startTime": "2026-11-20T09:00:00Z",
                        "lastUpdated": "2026-11-20T09:01:00Z",
                    },
                    {"$set": {"lastUpdated": "2026-11-20T10:30:00Z"}},
                ],
            )

            self.assertEqual(
                get_session_last_updated(new_sess),
                datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc),
            )

            # Cutoff after old_sess, before new_sess's $set.lastUpdated
            found = find_gemini_session(
                repo,
                after=datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc),
                gemini_dir=gemini_dir,
            )
            self.assertEqual(found, new_sess)

            # Cutoff after both sessions -> None
            none_found = find_gemini_session(
                repo,
                after=datetime(2026, 11, 21, 0, 0, 0, tzinfo=timezone.utc),
                gemini_dir=gemini_dir,
            )
            self.assertIsNone(none_found)

    def test_full_sha256_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "legacy-repo"
            repo.mkdir()
            gemini_dir = root / ".gemini"

            real_repo = os.path.realpath(str(repo))
            full_sha = hashlib.sha256(real_repo.encode("utf-8")).hexdigest()
            ids = resolve_gemini_project_ids(repo, gemini_dir=gemini_dir)
            self.assertIn(full_sha, ids)

            sess = (
                gemini_dir
                / "tmp"
                / full_sha
                / "chats"
                / "session-2026-11-20T11-00-cccc3333.jsonl"
            )
            _write_jsonl(
                sess,
                [
                    {
                        "sessionId": "cccc3333",
                        "projectHash": full_sha,
                        "startTime": "2026-11-20T11:00:00Z",
                        "lastUpdated": "2026-11-20T11:05:00Z",
                    }
                ],
            )
            found = find_gemini_session(repo, gemini_dir=gemini_dir)
            self.assertEqual(found, sess)

    def test_light_trimming_preserves_file_diff_and_caps_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / "session-2026-11-20T11-00-dddd4444.jsonl"
            huge_file = "x = 1\n" * 6000  # > 20 KB
            huge_shell_out = "LINE_START\n" + ("stdout line\n" * 3000) + "LINE_END"

            _write_jsonl(
                sess,
                [
                    {
                        "sessionId": "dddd4444",
                        "projectHash": "demo",
                        "startTime": "2026-11-20T11:00:00Z",
                    },
                    {
                        "id": "m1",
                        "type": "gemini",
                        "content": [{"text": "Applying edit"}],
                        "tokens": {"input": 1000, "output": 200},
                        "displayContent": "ui copy",
                        "displayName": "Gemini",
                        "renderOutputAsMarkdown": True,
                        "thoughts": [{"subject": "Plan", "description": "Wrap request"}],
                        "toolCalls": [
                            {
                                "id": "tc1",
                                "name": "replace",
                                "args": {
                                    "file_path": "app.py",
                                    "instruction": "Add retry logic",
                                },
                                "displayName": "Edit File",
                                "renderOutputAsMarkdown": False,
                                "result": [{"text": huge_shell_out}],
                                "resultDisplay": {
                                    "fileDiff": "@@ -1 +1 @@",
                                    "fileName": "app.py",
                                    "filePath": "app.py",
                                    "originalContent": huge_file,
                                    "newContent": huge_file + "y = 2\n",
                                },
                            },
                            {
                                "id": "tc2",
                                "name": "run_shell_command",
                                "args": {"command": "pytest"},
                                "result": huge_shell_out,
                                "resultDisplay": huge_shell_out,
                            },
                        ],
                    },
                ],
            )

            trimmed = load_and_trim_session(sess, agent_version="0.64.0")
            self.assertEqual(trimmed["agent"], "gemini-cli")
            self.assertEqual(trimmed["agent_version"], "0.64.0")
            self.assertEqual(len(trimmed["lines"]), 2)

            msg = trimmed["lines"][1]
            self.assertEqual(msg["tokens"], {"input": 1000, "output": 200})  # kept for per-tool token metrics
            self.assertNotIn("displayContent", msg)
            self.assertNotIn("displayName", msg)
            self.assertNotIn("renderOutputAsMarkdown", msg)
            self.assertEqual(msg["thoughts"][0]["subject"], "Plan")

            tc1, tc2 = msg["toolCalls"]
            self.assertNotIn("displayName", tc1)
            self.assertNotIn("renderOutputAsMarkdown", tc1)
            # FileDiff originalContent / newContent preserved in FULL (>20KB)
            self.assertEqual(tc1["resultDisplay"]["originalContent"], huge_file)
            self.assertEqual(tc1["resultDisplay"]["newContent"], huge_file + "y = 2\n")
            # Tool result capped at ~20KB with head+tail preserved
            self.assertIn("…[truncated ", tc1["result"][0]["text"])
            self.assertIn("LINE_START", tc1["result"][0]["text"])
            self.assertIn("LINE_END", tc1["result"][0]["text"])

            self.assertIn("…[truncated ", tc2["result"])
            self.assertIn("…[truncated ", tc2["resultDisplay"])


if __name__ == "__main__":
    unittest.main()
