"""Local secret scanning and redaction engine for CLI pre-push hook."""

from __future__ import annotations

import os
import re
from pathlib import Path

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_token", re.compile(r"\b(ghp_[A-Za-z0-9_]{36}|github_pat_[A-Za-z0-9_]{82})\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b")),
    ("aws_access_key", re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-[a-zA-Z0-9]{32,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b")),
    ("stripe_key", re.compile(r"\b(sk|pk)_(test|live)_[0-9a-zA-Z]{24,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")),
]


class SecretScanner:
    """Scans and scrubs sensitive tokens and credentials before sending to server."""

    def __init__(self, repo_dir: Path | None = None) -> None:
        self.exact_secrets: set[str] = set()
        self._load_env_secrets(repo_dir)

    def _load_env_secrets(self, repo_dir: Path | None) -> None:
        # Load from process environment
        for k, v in os.environ.items():
            if any(term in k.upper() for term in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                if len(v) >= 8:
                    self.exact_secrets.add(v)

        # Load from .env files
        if repo_dir and repo_dir.exists():
            for env_path in repo_dir.glob(".env*"):
                if env_path.is_file():
                    try:
                        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                            line = line.strip()
                            if "=" in line and not line.startswith("#"):
                                _, _, val = line.partition("=")
                                val = val.strip().strip("'\"")
                                if len(val) >= 6:
                                    self.exact_secrets.add(val)
                    except Exception:
                        pass

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        """Redact secrets from text and return cleaned text plus redaction counts."""
        counts: dict[str, int] = {}

        # 1. Redact regex patterns
        for name, pattern in SECRET_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                counts[name] = counts.get(name, 0) + len(matches)
                text = pattern.sub(f"[REDACTED:{name.upper()}]", text)

        # 2. Redact exact env secrets
        for s in self.exact_secrets:
            if s in text:
                occurrences = text.count(s)
                counts["env_secret"] = counts.get("env_secret", 0) + occurrences
                text = text.replace(s, "[REDACTED:SECRET]")

        return text, counts
