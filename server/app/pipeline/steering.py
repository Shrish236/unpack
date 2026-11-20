"""Steering: the instructions and skills an agent was given, read from the repo at the pushed commit.

The agent was steered by files like GEMINI.md and skill folders. Unpack reads them at the head commit,
splits them into rules, and gives the rules to the decision pass so it can say which rule applied to a
decision and whether the agent followed it. A repo with no steering files simply has no rules.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .repos import read_file_at

# Antigravity CLI and Gemini CLI first. The others are read when present.
STEERING_FILES = (
    "GEMINI.md", ".gemini/GEMINI.md", "AGENTS.md", ".agents/AGENTS.md", "CLAUDE.md",
)
STEERING_DIRS = (".agents/rules", ".agents/skills", ".agent/rules", ".agent/skills", ".gemini/skills")
MAX_RULES = 60
MAX_RULE_CHARS = 280
MAX_FILE_BYTES = 40_000

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,4}\s+(.*\S)\s*$")


@dataclass
class SteeringRule:
    id: str  # S1, S2 ... stable within one snapshot
    text: str
    source: str  # the file it came from
    section: str  # the nearest heading


@dataclass
class SteeringSnapshot:
    files: dict[str, str]  # path -> sha256 of content
    rules: list[SteeringRule]

    def as_json(self) -> dict:
        return {
            "files": self.files,
            "rules": [{"id": r.id, "text": r.text, "source": r.source, "section": r.section} for r in self.rules],
        }


def _list_dir(mirror: Path, sha: str, folder: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(mirror), "ls-tree", "-r", "--name-only", sha, "--", folder],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return []
    return [p for p in proc.stdout.decode("utf-8", "replace").splitlines() if p.lower().endswith(".md")]


def parse_rules(path: str, text: str, start_index: int = 1) -> list[SteeringRule]:
    """Every bullet or numbered line under a heading is one rule. Prose lines are not rules."""
    rules: list[SteeringRule] = []
    section = path
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(1)
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and len(bullet.group(1)) >= 12:
            rules.append(SteeringRule(
                id=f"S{start_index + len(rules)}", text=bullet.group(1)[:MAX_RULE_CHARS], source=path, section=section,
            ))
    return rules


def read_steering(mirror: Path, sha: str) -> SteeringSnapshot:
    contents: dict[str, str] = {}
    for path in STEERING_FILES:
        try:
            contents[path] = read_file_at(mirror, sha, path)[:MAX_FILE_BYTES].decode("utf-8", "replace")
        except (subprocess.CalledProcessError, OSError):
            continue
    for folder in STEERING_DIRS:
        for path in _list_dir(mirror, sha, folder)[:20]:
            try:
                contents[path] = read_file_at(mirror, sha, path)[:MAX_FILE_BYTES].decode("utf-8", "replace")
            except (subprocess.CalledProcessError, OSError):
                continue

    rules: list[SteeringRule] = []
    for path, text in contents.items():
        rules.extend(parse_rules(path, text, start_index=len(rules) + 1))
        if len(rules) >= MAX_RULES:
            rules = rules[:MAX_RULES]
            break
    return SteeringSnapshot(
        files={p: hashlib.sha256(t.encode("utf-8")).hexdigest()[:16] for p, t in contents.items()},
        rules=rules,
    )
