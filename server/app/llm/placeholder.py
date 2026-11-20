"""Compatibility shim kept after replacing placeholder reasoning with server.app.llm.client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningResult:
    enabled: bool
    summary: str = ""
    reasons: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    rejected_count: int = 0
