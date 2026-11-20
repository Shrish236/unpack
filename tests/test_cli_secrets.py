"""Tests for cli.secrets."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli.secrets import SecretScanner


class TestSecretScanner(unittest.TestCase):
    def test_regex_patterns_and_full_pem_block(self) -> None:
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0123456789abcdef\n"
            "secretBodyLineThatMustNeverLeak99\n"
            "-----END RSA PRIVATE KEY-----"
        )
        gh_tok = "ghp_" + "A" * 36
        google_key = "AIza" + "B" * 35
        aws_key = "AKIA" + "C" * 16
        anth_key = "sk-ant-" + "D" * 28
        openai_key = "sk-" + "E" * 36
        slack_tok = "xoxb-1234567890-abcdef123456"
        stripe_key = "sk_live_" + "F" * 26
        jwt_tok = (
            "eyJhbGciOiJIUzI1NiJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6y"
        )
        conn = "postgresql://admin:Sup3rS3cret!@db.example.com:5432/prod"
        assign = 'password = "my_plaintext_pw_123"'

        sample = "\n".join(
            [
                pem,
                gh_tok,
                google_key,
                aws_key,
                anth_key,
                openai_key,
                slack_tok,
                stripe_key,
                jwt_tok,
                conn,
                assign,
            ]
        )

        scanner = SecretScanner(repo_dir=None, include_process_env=False)
        redacted, counts = scanner.redact(sample)

        for leaked in (
            "secretBodyLineThatMustNeverLeak99",
            gh_tok,
            google_key,
            aws_key,
            anth_key,
            openai_key,
            slack_tok,
            stripe_key,
            jwt_tok,
            "Sup3rS3cret!",
            "my_plaintext_pw_123",
        ):
            self.assertNotIn(leaked, redacted)

        self.assertEqual(counts["private_key"], 1)
        self.assertEqual(counts["github_token"], 1)
        self.assertEqual(counts["google_api_key"], 1)
        self.assertEqual(counts["aws_access_key"], 1)
        self.assertEqual(counts["anthropic_key"], 1)
        self.assertEqual(counts["openai_key"], 1)
        self.assertEqual(counts["slack_token"], 1)
        self.assertEqual(counts["stripe_key"], 1)
        self.assertEqual(counts["jwt"], 1)
        self.assertEqual(counts["connection_string"], 1)
        self.assertEqual(counts["secret_assignment"], 1)

    def test_env_files_and_process_env_and_recursive_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".env").write_text(
                "CUSTOM_DB_PASS=ultra_secret_db_value\nSHORT=abc\nFLAG=true\n",
                encoding="utf-8",
            )
            (repo / ".env.example").write_text(
                "EXAMPLE_VAL=do_not_load_from_example\n",
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {
                    "MY_CUSTOM_API_TOKEN": "proc_secret_token_987654",
                    "SSH_KEY_PATH": "/Users/dev/.ssh/id_rsa",
                },
                clear=False,
            ):
                scanner = SecretScanner(repo_dir=repo, include_process_env=True)
                obj = {
                    "lines": [
                        {
                            "content": "Using ultra_secret_db_value and proc_secret_token_987654",
                            "path": "/Users/dev/.ssh/id_rsa",
                            "example": "do_not_load_from_example",
                        }
                    ]
                }
                scrubbed, counts = scanner.redact_value(obj)

            entry = scrubbed["lines"][0]
            self.assertNotIn("ultra_secret_db_value", entry["content"])
            self.assertNotIn("proc_secret_token_987654", entry["content"])
            self.assertIn("[REDACTED:env_value]", entry["content"])
            self.assertIn("[REDACTED:env_var]", entry["content"])
            # Process env file paths and .env.example placeholders are NOT redacted
            self.assertEqual(entry["path"], "/Users/dev/.ssh/id_rsa")
            self.assertEqual(entry["example"], "do_not_load_from_example")
            self.assertEqual(counts.get("env_value"), 1)
            self.assertEqual(counts.get("env_var"), 1)

    def test_high_entropy_redacts_secrets_but_ignores_shas_and_uuids(self) -> None:
        scanner = SecretScanner(repo_dir=None, include_process_env=False)
        high_ent = "aB3dE6fG9hI2jK5lM8nO1pQ4rS7tU0vW3xY6zA9bC2dE"
        git_sha = "808199f1234567890abcdef1234567890abcdef1"
        uuid_val = "60f88577-c514-40f4-8a96-718010ef608e"

        text = (
            f'signing_material = "{high_ent}"\n'
            f'commit_sha = "{git_sha}"\n'
            f'session_id = "{uuid_val}"\n'
        )
        scrubbed, counts = scanner.redact(text)
        self.assertNotIn(high_ent, scrubbed)
        self.assertIn("[REDACTED:high_entropy]", scrubbed)
        self.assertIn(git_sha, scrubbed)
        self.assertIn(uuid_val, scrubbed)
        self.assertEqual(counts.get("high_entropy"), 1)


if __name__ == "__main__":
    unittest.main()
