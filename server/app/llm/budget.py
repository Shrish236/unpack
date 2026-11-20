"""Token budget shared by every LLM call of one push.

The daily budget is read once when the job starts. Without this, each call of a push would check the same stale
number and a push with three calls could overshoot. A quota error from the API also lands here, so the calls
after it are skipped instead of each burning retries on a quota that is already gone.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from .client import LLMInvocationResult


@dataclass
class LLMBudget:
    used: int = 0  # tokens already spent today by this repo, plus what this push has spent so far
    quota_hit: bool = False

    def exhausted(self) -> bool:
        return self.quota_hit or self.used >= settings.GEMINI_DAILY_TOKEN_BUDGET_PER_REPO

    def reason(self) -> str:
        return "the Gemini quota is used up" if self.quota_hit else "daily token budget exceeded for repository"

    def record(self, res: LLMInvocationResult) -> None:
        self.used += res.tokens_used
        if res.quota:
            self.quota_hit = True

    def record_tokens(self, tokens: int) -> None:
        self.used += tokens
