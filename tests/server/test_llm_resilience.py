"""Quota handling, token budget and prompt fitting for the structured Gemini calls. The client is a fake."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from server.app.config import settings
from server.app.llm.budget import LLMBudget
from server.app.llm.client import (
    LLMBackendError, LLMInvocationResult, LLMQuotaError, RawLLMResponse, fit_prompt, is_quota_error, run_structured_llm,
)


class _Out(BaseModel):
    x: int = 0


class _Fake:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    async def generate_json(self, **kwargs):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_quota_markers():
    assert is_quota_error("429 RESOURCE_EXHAUSTED: quota exceeded")
    assert is_quota_error(LLMQuotaError("x"))
    assert not is_quota_error("connection reset")


@pytest.mark.asyncio
async def test_quota_on_every_model_tries_each_once_then_gives_up():
    fake = _Fake([LLMBackendError("429 RESOURCE_EXHAUSTED: Please retry in 2h3m4.5s")] * 10)
    res = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    models = 1 + len([m for m in settings.GEMINI_MODEL_FALLBACK.split(",") if m.strip()])
    assert fake.calls == models  # one call per model: no retry on the same model, no repair call
    assert res.output is None and res.quota and res.error.startswith("quota")
    assert [c.status for c in res.calls] == ["quota"] * models
    # and the next call skips every model without sending anything
    before = fake.calls
    again = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    assert fake.calls == before and again.quota and not again.calls


@pytest.mark.asyncio
async def test_quota_on_the_primary_model_falls_through_to_the_next_one():
    ok = RawLLMResponse(text='{"x": 7}', model="fallback-model", input_tokens=5, output_tokens=2)
    fake = _Fake([LLMBackendError("429 RESOURCE_EXHAUSTED: model: primary, limit: 20 per day"), ok])
    res = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    assert res.output.x == 7 and not res.quota and fake.calls == 2
    assert res.calls[0].status == "quota" and res.calls[1].status == "ok"
    # the primary is now cooling: the next call goes straight to the fallback
    fake2 = _Fake([ok])
    res2 = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake2)
    assert res2.output.x == 7 and fake2.calls == 1


def test_quota_cooldown_reads_the_apis_wait():
    from server.app.llm.client import quota_cooldown_s
    assert quota_cooldown_s("Please retry in 15h5m8.585435941s.") == 15 * 3600 + 5 * 60 + 8.585435941
    assert quota_cooldown_s("retry in 30s") == 30
    assert quota_cooldown_s("limit exceeded per day") == 3600 and quota_cooldown_s("slow down") == 60
    assert quota_cooldown_s("retry in 900h") == 24 * 3600  # capped


@pytest.mark.asyncio
async def test_other_errors_still_retry_then_fall_back():
    fake = _Fake([LLMBackendError("boom")] * 10)
    res = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    models = 1 + len([m for m in settings.GEMINI_MODEL_FALLBACK.split(",") if m.strip()])
    assert fake.calls == 2 * models and not res.quota  # two tries on each model


@pytest.mark.asyncio
async def test_tokens_used_and_budget_accumulate():
    fake = _Fake([RawLLMResponse(text='{"x": 1}', model="m", input_tokens=70, output_tokens=30)])
    res = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    assert res.tokens_used == 100
    b = LLMBudget(used=10)
    b.record(res)
    assert b.used == 110 and not b.exhausted()
    b.record(LLMInvocationResult(output=None, model=None, quota=True))
    assert b.exhausted() and "quota" in b.reason()


def test_budget_exhausted_by_tokens(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_DAILY_TOKEN_BUDGET_PER_REPO", 50)
    assert LLMBudget(used=50).exhausted()
    assert "budget" in LLMBudget(used=50).reason()


def test_fit_prompt_keeps_head_and_tail():
    short, trimmed = fit_prompt("abc", 1000)
    assert short == "abc" and not trimmed
    text = "HEAD" + "m" * 50_000 + "TAIL"
    out, trimmed = fit_prompt(text, 2000)
    assert trimmed and out.startswith("HEAD") and out.endswith("TAIL") and len(out) < len(text)
    assert "left out" in out

@pytest.mark.asyncio
async def test_final_error_names_what_went_wrong_on_each_model():
    errs = [LLMBackendError("503 UNAVAILABLE high demand")] * 2 + [LLMBackendError("429 RESOURCE_EXHAUSTED retry in 30s")] * 10
    fake = _Fake(errs)
    res = await run_structured_llm(system_prompt="s", user_prompt="u", schema=_Out, purpose="t", client=fake)
    primary = settings.GEMINI_MODEL_PRIMARY
    assert res.output is None and not res.quota  # not every model was out of quota: it was an overload first
    assert res.error.startswith(f"{primary}: overloaded (503)") and "quota used up" in res.error
