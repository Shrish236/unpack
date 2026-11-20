"""Placeholder for the reasoning step (Gemini calls, reasons, session review).

The real implementation replaces `generate_reasons`. Until then it returns no reasons, no
findings and no timeline, and the analysis carries the `reasons_unavailable` banner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import settings


@dataclass
class ReasoningResult:
    enabled: bool
    summary: str = ""
    reasons: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    rejected_count: int = 0


def generate_reasons(changed_node_ids: list[str], has_session: bool) -> ReasoningResult:
    """Returns the reasoning output for one analysis. Disabled in this build."""
    if not settings.REASONING_ENABLED:
        return ReasoningResult(enabled=False)
    raise NotImplementedError("reasoning is not built yet")
