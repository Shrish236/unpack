"""Tests for cli.git_info."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cli.git_info import (
    get_changed_files,
    get_commits,
    get_head_sha,
    get_oldest_commit_parent_time,
    get_repo_ref,
    get_unified_diff,
    parse_remote_url,
    resolve_base_sha,
)


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    merged_env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


class TestGitInfo(unittest.TestCase):
    def test_parse_remote_url_variants(self) -> None:
        self.assertEqual(
            parse_remote_url("git@github.com:encode/httpx.git"), ("encode", "httpx")
        )
        self.assertEqual(
            parse_remote_url("https://github.com/Shrish236/unpack.git"), ("Shrish236", "unpack")
        )
        self.assertEqual(
            parse_remote_url("ssh://git@github.com/my-org/my-repo"), ("my-org", "my-repo")
        )
        self.assertEqual(parse_remote_url("/tmp/remotes/acme/demo.git"), ("acme", "demo"))

    def test_merge_base_commits_and_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bare = root / "remote.git"
            work = root / "work"
            bare.mkdir()
            work.mkdir()

            _git(bare, "init", "--bare", "-b", "main")
            _git(work, "init", "-b", "main")
            _git(work, "remote", "add", "origin", str(bare))

            # Base commit on main
            (work / "keep.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            (work / "remove_me.py").write_text("x = 1\n", encoding="utf-8")
            (work / "old_name.py").write_text("def renamed():\n    return 42\n", encoding="utf-8")
            _git(work, "add", ".")
            _git(work, "commit", "-m", "initial commit")
            _git(work, "push", "-u", "origin", "main")
            main_sha = get_head_sha(work)

            # Create feature branch with two commits (simulating repeated push on PR)
            _git(work, "checkout", "-b", "feat/retries")
            (work / "keep.py").write_text("def a():\n    return 2\n", encoding="utf-8")
            (work / "added.py").write_text("def new_fn():\n    return True\n", encoding="utf-8")
            _git(work, "add", ".")
            _git(work, "commit", "-m", "commit 1: add retry helper")
            first_push_sha = get_head_sha(work)

            # Second commit: delete, rename, binary, and oversized text file
            (work / "remove_me.py").unlink()
            (work / "old_name.py").rename(work / "new_name.py")
            (work / "logo.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
            (work / "huge.txt").write_text("a" * 2048, encoding="utf-8")
            _git(work, "add", "-A")
            _git(work, "commit", "-m", "commit 2: rename, delete, binary, huge")
            head_sha = get_head_sha(work)

            # Even on a 2nd push (remote_sha=first_push_sha), base_sha uses merge-base (main)
            base_sha = resolve_base_sha(
                work,
                head_sha=head_sha,
                branch="feat/retries",
                default_branch="main",
                remote_sha=first_push_sha,
            )
            self.assertEqual(base_sha, main_sha)

            commits = get_commits(work, base_sha, head_sha)
            self.assertEqual(len(commits), 2)
            self.assertEqual(commits[0]["message"], "commit 1: add retry helper")
            self.assertEqual(commits[1]["message"], "commit 2: rename, delete, binary, huge")

            cutoff = get_oldest_commit_parent_time(work, commits, base_sha)
            self.assertIsNotNone(cutoff)

            diff_text = get_unified_diff(work, base_sha, head_sha)
            self.assertIn("return 2", diff_text)

            changed = get_changed_files(work, base_sha, head_sha, max_bytes=1024)
            by_path = {c["path"]: c for c in changed}

            self.assertEqual(by_path["keep.py"]["status"], "M")
            self.assertIn("return 1", by_path["keep.py"]["base_content"])
            self.assertIn("return 2", by_path["keep.py"]["head_content"])

            self.assertEqual(by_path["added.py"]["status"], "A")
            self.assertIsNone(by_path["added.py"]["base_content"])
            self.assertIn("new_fn", by_path["added.py"]["head_content"])

            self.assertEqual(by_path["remove_me.py"]["status"], "D")
            self.assertIn("x = 1", by_path["remove_me.py"]["base_content"])
            self.assertIsNone(by_path["remove_me.py"]["head_content"])

            self.assertEqual(by_path["new_name.py"]["status"], "R")
            self.assertEqual(by_path["new_name.py"]["old_path"], "old_name.py")

            self.assertTrue(by_path["logo.bin"]["is_binary"])
            self.assertIsNone(by_path["logo.bin"]["head_content"])
            self.assertFalse(by_path["logo.bin"]["truncated"])

            self.assertFalse(by_path["huge.txt"]["is_binary"])
            self.assertTrue(by_path["huge.txt"]["truncated"])
            self.assertIsNone(by_path["huge.txt"]["head_content"])

            repo_ref = get_repo_ref(work)
            self.assertEqual(repo_ref["default_branch"], "main")
            self.assertEqual(repo_ref["name"], "remote")


if __name__ == "__main__":
    unittest.main()
