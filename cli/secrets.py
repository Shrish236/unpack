"""Local secret scanning and redaction engine for the Unpack CLI."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

# Specific secret patterns checked before generic assignments/entropy.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
        ),
    ),
    ("private_key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    (
        "connection_string",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|rediss?|amqps?)://"
            r"[^\s:/@'\"`]+:[^\s@'\"`]+@"
        ),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    ),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9\-_]{32,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,64}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[0-9A-Za-z]{24,}\b")),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9\-_=]{10,}\.eyJ[A-Za-z0-9\-_=]{10,}\.[A-Za-z0-9\-_.+/=]{10,}\b"
        ),
    ),
]

# Key-value assignment pattern for passwords and generic secrets.
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:password|passwd|pwd|secret|api_key|apikey|access_token|auth_token|"
    r"client_secret|private_key)\s*[:=]\s*[\"']?)([^\s\"'`,;}\]]{6,})([\"']?)"
)

# High-entropy token (>= 32 chars) inside an assignment expression.
HIGH_ENTROPY_ASSIGNMENT_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_.-]*\s*[:=]\s*[\"']?)([A-Za-z0-9+/=_\-]{32,})([\"']?)"
)

_HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{32,64}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_TRIVIAL_ENV_VALUES = frozenset(
    {
        "true",
        "false",
        "yes",
        "no",
        "none",
        "null",
        "default",
        "changeme",
        "localhost",
        "127.0.0.1",
        "development",
        "production",
        "test",
    }
)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    freq: dict[str, int] = {}
    for ch in value:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def _has_mixed_char_classes(value: str) -> bool:
    classes = sum(
        [
            any(c.islower() for c in value),
            any(c.isupper() for c in value),
            any(c.isdigit() for c in value),
            any(c in "+/=_-" for c in value),
        ]
    )
    return classes >= 3


def _is_ignored_env_value(value: str, *, is_process_env: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in _TRIVIAL_ENV_VALUES:
        return True
    if lowered.startswith("[redacted:"):
        return True
    if is_process_env:
        # Skip local filesystem paths, PATH-like lists, and plain host URLs
        if value.startswith(("/", "~/", "./", "http://", "https://")):
            return True
        if os.pathsep in value and "/" in value:
            return True
    return False


class SecretScanner:
    """Scans and redacts secrets from text and nested JSON structures."""

    def __init__(
        self,
        repo_dir: Path | None = None,
        *,
        include_process_env: bool = True,
    ) -> None:
        self.env_file_secrets: list[str] = []
        self.env_var_secrets: list[str] = []
        self._load_secrets(repo_dir, include_process_env=include_process_env)

    def _load_secrets(self, repo_dir: Path | None, *, include_process_env: bool) -> None:
        file_vals: set[str] = set()
        if repo_dir and repo_dir.exists():
            for env_path in sorted(repo_dir.glob(".env*")):
                if not env_path.is_file():
                    continue
                if env_path.name.endswith((".example", ".sample", ".template")):
                    continue
                try:
                    for raw_line in env_path.read_text(
                        encoding="utf-8", errors="ignore"
                    ).splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        if line.startswith("export "):
                            line = line[len("export ") :].strip()
                        _, _, val = line.partition("=")
                        val = val.strip()
                        # Strip inline comments only if unquoted
                        if val and val[0] not in ("'", '"') and " #" in val:
                            val = val.split(" #", 1)[0].strip()
                        val = val.strip("'\"")
                        if len(val) >= 6 and not _is_ignored_env_value(
                            val, is_process_env=False
                        ):
                            file_vals.add(val)
                except OSError:
                    pass

        proc_vals: set[str] = set()
        if include_process_env:
            for key, val in os.environ.items():
                upper_key = key.upper()
                if any(term in upper_key for term in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                    if (
                        len(val) >= 8
                        and val not in file_vals
                        and not _is_ignored_env_value(val, is_process_env=True)
                    ):
                        proc_vals.add(val)

        # Longest first so shorter substrings do not break longer secret matches.
        self.env_file_secrets = sorted(file_vals, key=len, reverse=True)
        self.env_var_secrets = sorted(proc_vals, key=len, reverse=True)

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        """Redact secrets from a string and return (scrubbed_text, redaction_counts)."""
        counts: dict[str, int] = {}
        if not text:
            return text, counts

        def _bump(kind: str, n: int = 1) -> None:
            if n > 0:
                counts[kind] = counts.get(kind, 0) + n

        # 1. Exact typed patterns (PEM blocks, connection strings, provider tokens, JWTs)
        for kind, pattern in SECRET_PATTERNS:
            text, n = pattern.subn(f"[REDACTED:{kind}]", text)
            _bump(kind, n)

        # 2. Exact values from repo .env* files
        for secret in self.env_file_secrets:
            if secret in text:
                n = text.count(secret)
                text = text.replace(secret, "[REDACTED:env_value]")
                _bump("env_value", n)

        # 3. Exact values from secret-named process environment variables
        for secret in self.env_var_secrets:
            if secret in text:
                n = text.count(secret)
                text = text.replace(secret, "[REDACTED:env_var]")
                _bump("env_var", n)

        # 4. Generic password= / secret= assignments
        def _replace_assignment(match: re.Match[str]) -> str:
            prefix, val, suffix = match.group(1), match.group(2), match.group(3)
            if val.startswith("[REDACTED:") or val.lower() in _TRIVIAL_ENV_VALUES:
                return match.group(0)
            _bump("secret_assignment", 1)
            return f"{prefix}[REDACTED:secret_assignment]{suffix}"

        text = SECRET_ASSIGNMENT_RE.sub(_replace_assignment, text)

        # 5. High-entropy tokens (>= 32 chars) in assignments
        def _replace_entropy(match: re.Match[str]) -> str:
            prefix, val, suffix = match.group(1), match.group(2), match.group(3)
            if val.startswith("[REDACTED:"):
                return match.group(0)
            if _HEX_SHA_RE.match(val) or _UUID_RE.match(val):
                return match.group(0)
            if _has_mixed_char_classes(val) and _shannon_entropy(val) >= 4.3:
                _bump("high_entropy", 1)
                return f"{prefix}[REDACTED:high_entropy]{suffix}"
            return match.group(0)

        text = HIGH_ENTROPY_ASSIGNMENT_RE.sub(_replace_entropy, text)

        return text, counts

    def redact_value(
        self, obj: Any, counts: dict[str, int] | None = None
    ) -> tuple[Any, dict[str, int]]:
        """Recursively redact every string inside a JSON-compatible object."""
        totals = counts if counts is not None else {}

        if isinstance(obj, str):
            scrubbed, c = self.redact(obj)
            for k, v in c.items():
                totals[k] = totals.get(k, 0) + v
            return scrubbed, totals
        if isinstance(obj, list):
            return [self.redact_value(item, totals)[0] for item in obj], totals
        if isinstance(obj, dict):
            return {k: self.redact_value(v, totals)[0] for k, v in obj.items()}, totals
        return obj, totals
