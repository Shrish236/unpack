"""Gemini API client wrapper with retries, model fallback, JSON repair, and call logging (§4.7)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from ..config import settings
from .prompt_builder import load_repair_prompt

log = logging.getLogger("unpack.llm")


# -------------------------------------------------------------
# Structured LLM output schema (passed to Gemini response_schema)
# -------------------------------------------------------------


class LLMEvidenceQuote(BaseModel):
    turn: str
    quote: str


class LLMHistoryStep(BaseModel):
    turn: str
    text: str


class LLMFunctionReason(BaseModel):
    fn: str
    reason: str
    driver: Literal["user_asked", "agent_decided", "not_stated"]
    history: list[LLMHistoryStep] = Field(default_factory=list)
    evidence: list[LLMEvidenceQuote] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "high"


class LLMReviewFinding(BaseModel):
    kind: Literal[
        "claim_not_backed",
        "test_failed_ignored",
        "not_tested_after_change",
        "request_not_done",
        "check_weakened",
        "dead_end",
    ]
    finding: str
    functions: list[str] = Field(default_factory=list)
    evidence: list[LLMEvidenceQuote] = Field(default_factory=list)


class LLMReasoningOutput(BaseModel):
    summary: str = ""
    functions: list[LLMFunctionReason] = Field(default_factory=list)
    session_review: list[LLMReviewFinding] = Field(default_factory=list)


DecisionType = Literal["architecture", "design", "dependency", "retries", "test", "scope", "other"]


class LLMDecision(BaseModel):
    turn: str  # the turn where the decision happened (a user turn for human decisions)
    actor: Literal["agent", "human"]
    kind: Literal["choice", "redirect", "reject", "requirement", "discussion"]
    type: DecisionType
    proposal: str = ""  # what was on the table (the agent's plan, or what the human was reacting to)
    choice: str = ""  # what was decided
    statement: str = ""  # a general, reusable rule that captures the decision ("Do not add runtime dependencies")
    quote: str = ""  # verbatim from the turn
    rule_id: str | None = None  # a steering rule from ## STEERING that applies to this decision
    rule_followed: bool | None = None  # whether the agent's action followed that rule
    nodes: list[str] = Field(default_factory=list)  # changed-function ids this decision is about


class LLMHighlight(BaseModel):
    kind: Literal["went_right", "went_wrong"]
    text: str
    turn: str
    quote: str = ""
    nodes: list[str] = Field(default_factory=list)


class LLMDecisionOutput(BaseModel):
    decisions: list[LLMDecision] = Field(default_factory=list)
    highlights: list[LLMHighlight] = Field(default_factory=list)


FlowRole = Literal["entry", "logic", "persistence", "io", "test", "glue"]


class LLMFlowStep(BaseModel):
    fn: str  # a label from the prompt (F1, F2 ...)
    role: FlowRole = "logic"
    note: str = ""


class LLMFlowStage(BaseModel):
    title: str
    summary: str = ""
    steps: list[LLMFlowStep] = Field(default_factory=list)


class LLMFlowOutput(BaseModel):
    stages: list[LLMFlowStage] = Field(default_factory=list)
    uncovered: list[str] = Field(default_factory=list)


# -------------------------------------------------------------
# Transport & Call Logging Records
# -------------------------------------------------------------


@dataclass
class RawLLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int | None = None
    finish_reason: str | None = None


@dataclass
class LLMCallRecord:
    purpose: str  # reasons | json_repair
    model: str
    attempt: int
    prompt_version: int
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int | None = None
    latency_ms: int = 0
    status: str = "ok"
    error: str | None = None
    finish_reason: str | None = None
    request_hash: str | None = None
    response_text: str | None = None


@dataclass
class LLMInvocationResult:
    output: Any | None
    model: str | None
    calls: list[LLMCallRecord] = field(default_factory=list)
    error: str | None = None
    quota: bool = False  # the failure was a quota / rate limit, so the caller should not try again today

    @property
    def tokens_used(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)


class LLMBackendError(RuntimeError):
    """Raised by an LLM backend when a request fails."""


class LLMQuotaError(LLMBackendError):
    """The API refused because a quota or rate limit is used up. Retrying or switching model will not help."""


_QUOTA_MARKERS = ("429", "resource_exhausted", "quota", "rate limit", "rate_limit", "too many requests")


def is_quota_error(exc: BaseException | str) -> bool:
    if isinstance(exc, LLMQuotaError):
        return True
    text = str(exc).lower()
    return any(m in text for m in _QUOTA_MARKERS)


def _wrap_backend_error(exc: Exception) -> LLMBackendError:
    msg = f"Gemini API error ({type(exc).__name__}): {exc}"
    return LLMQuotaError(msg) if is_quota_error(exc) else LLMBackendError(msg)


# Quotas are per model (the free tier allows 20 requests a day for each one), so a model whose quota is gone is skipped
# for as long as the API said, and the next model is tried. model -> time.monotonic() until which it is skipped.
_cooldown: dict[str, float] = {}
_RETRY_IN = re.compile(r"retry in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", re.I)


def quota_cooldown_s(message: str) -> float:
    """How long to leave a model alone after a quota error: what the API says ("Please retry in 15h5m8s"), else a guess."""
    m = _RETRY_IN.search(message)
    if m and any(m.groups()):
        h, mi, s = (float(g) if g else 0.0 for g in m.groups())
        return max(5.0, min(h * 3600 + mi * 60 + s, 24 * 3600))
    return 3600.0 if re.search(r"per day|daily", message, re.I) else 60.0


def short_failure(message: str) -> str:
    """One plain phrase for why a model call failed, for banners and logs."""
    m = message or ""
    if is_quota_error(m):
        return "quota used up"
    if "503" in m or "UNAVAILABLE" in m:
        return "overloaded (503)"
    if "504" in m or "DEADLINE_EXCEEDED" in m or "timed out" in m.lower():
        return "timed out"
    if "404" in m or "NOT_FOUND" in m:
        return "model not found"
    if "parse failed" in m:
        return "returned invalid JSON"
    return m.replace("\n", " ")[:80]


def model_cooling(model: str) -> bool:
    until = _cooldown.get(model)
    return until is not None and until > time.monotonic()


def reset_cooldowns() -> None:
    _cooldown.clear()


def mark_quota_used(model: str, message: str) -> None:
    """Skip `model` until its quota resets (the API's own wait when it gives one)."""
    _cooldown[model] = time.monotonic() + quota_cooldown_s(message)


def model_order() -> list[str]:
    """Primary first, then each comma separated fallback, without repeats."""
    order = [settings.GEMINI_MODEL_PRIMARY]
    for extra in settings.GEMINI_MODEL_FALLBACK.split(","):
        if extra.strip() and extra.strip() not in order:
            order.append(extra.strip())
    return order


def first_available_model() -> str | None:
    """The first model in `model_order()` whose quota is not known to be used up."""
    return next((m for m in model_order() if not model_cooling(m)), None)


_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None


def _llm_slot() -> asyncio.Semaphore:
    """One semaphore per event loop, sized by GEMINI_CONCURRENCY, shared by every Gemini call."""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(max(1, settings.GEMINI_CONCURRENCY))
        _semaphore_loop = loop
    return _semaphore


def fit_prompt(user_prompt: str, max_input_tokens: int) -> tuple[str, bool]:
    """Keep a prompt under the input-token limit (about 4 characters a token). It cuts from the middle of the
    prompt: the task and the facts at the top and the latest turns at the bottom are the parts that matter."""
    limit = max(1000, int(max_input_tokens * 3.5))
    if len(user_prompt) <= limit:
        return user_prompt, False
    keep_head = int(limit * 0.35)
    keep_tail = limit - keep_head - 80
    cut = len(user_prompt) - keep_head - keep_tail
    return user_prompt[:keep_head] + f"\n\n[... {cut} characters of the middle left out to fit the model's input limit ...]\n\n" + user_prompt[-keep_tail:], True


class LLMClient(Protocol):
    async def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        temperature: float | None,
        max_output_tokens: int,
        timeout_s: int,
    ) -> RawLLMResponse: ...


class GoogleGenAIClient:
    """Real Gemini API client via the official `google-genai` SDK."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
        temperature: float | None,
        max_output_tokens: int,
        timeout_s: int,
    ) -> RawLLMResponse:
        if not self._api_key:
            raise LLMBackendError("GEMINI_API_KEY is not set")

        def _call() -> RawLLMResponse:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key)
            cfg_kwargs: dict[str, Any] = {
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "max_output_tokens": max_output_tokens,
            }
            if temperature is not None:
                cfg_kwargs["temperature"] = temperature

            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
            usage = getattr(response, "usage_metadata", None)
            in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
            out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
            think_raw = getattr(usage, "thoughts_token_count", None)
            think_tok = int(think_raw) if think_raw is not None else None

            finish = None
            cands = getattr(response, "candidates", None) or []
            if cands:
                fr = getattr(cands[0], "finish_reason", None)
                finish = str(fr) if fr is not None else None

            return RawLLMResponse(
                text=response.text or "",
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                thinking_tokens=think_tok,
                finish_reason=finish,
            )

        try:
            return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise LLMBackendError(f"Gemini call timed out after {timeout_s}s") from exc
        except LLMBackendError:
            raise
        except Exception as exc:
            raise _wrap_backend_error(exc) from exc

    async def generate_text_with_tools(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[Any],
        max_calls: int,
        timeout_s: int,
    ) -> RawLLMResponse:
        """Free-text answer where the model may call `tools` (plain Python functions) along the way."""
        if not self._api_key:
            raise LLMBackendError("GEMINI_API_KEY is not set")

        def _call() -> RawLLMResponse:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=max_calls),
                    max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                ),
            )
            text = response.text or ""
            usage = getattr(response, "usage_metadata", None)
            in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
            out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
            if not text.strip():
                # The model used up its tool calls before it wrote anything. Ask once more, with no tools, from
                # what the lookups returned.
                results = []
                for content in getattr(response, "automatic_function_calling_history", None) or []:
                    for part in getattr(content, "parts", None) or []:
                        fr = getattr(part, "function_response", None)
                        if fr is not None:
                            results.append(f"{fr.name}: {str(fr.response)[:1200]}")
                if results:
                    second = client.models.generate_content(
                        model=model,
                        contents=user_prompt + "\n\nLookup results so far:\n" + "\n".join(results[-40:])
                        + "\n\nNo more lookups. Write the notes now.",
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt, max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                        ),
                    )
                    text = second.text or ""
                    usage2 = getattr(second, "usage_metadata", None)
                    in_tok += int(getattr(usage2, "prompt_token_count", 0) or 0)
                    out_tok += int(getattr(usage2, "candidates_token_count", 0) or 0)
            return RawLLMResponse(text=text, model=model, input_tokens=in_tok, output_tokens=out_tok)

        try:
            return await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise LLMBackendError(f"Gemini tool call timed out after {timeout_s}s") from exc
        except Exception as exc:
            raise _wrap_backend_error(exc) from exc


_override_client: LLMClient | None = None


def set_llm_client(client: LLMClient | None) -> None:
    """Inject a fake/custom LLMClient in tests (mirrors services.set_github)."""
    global _override_client
    _override_client = client


_mock_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _mock_client
    if _override_client is not None:
        return _override_client
    if settings.GEMINI_BACKEND == "mock":  # no key, no quota: see llm/mock.py
        if _mock_client is None:
            from .mock import MockLLMClient
            _mock_client = MockLLMClient()
        return _mock_client
    return GoogleGenAIClient(settings.GEMINI_API_KEY)


def _temperature_for_model(model: str) -> float | None:
    """Gemini 3 uses the model default; Gemini 2.x uses deterministic temperature=0."""
    if "gemini-3" in model.lower():
        return None
    return 0.0


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json(text: str, schema: type[BaseModel]) -> Any:
    cleaned = _strip_code_fence(text)
    obj = json.loads(cleaned)
    return schema.model_validate(obj)


def _parse_reasoning_json(text: str) -> LLMReasoningOutput:
    return _parse_json(text, LLMReasoningOutput)


async def run_reasoning_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    prompt_version: int = 1,
    daily_tokens_used: int = 0,
    client: LLMClient | None = None,
) -> LLMInvocationResult:
    """Run one structured Gemini reasoning call with retry, fallback, and JSON repair."""
    return await run_structured_llm(
        system_prompt=system_prompt, user_prompt=user_prompt, schema=LLMReasoningOutput, purpose="reasons",
        prompt_version=prompt_version, daily_tokens_used=daily_tokens_used, client=client,
    )


async def run_structured_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    purpose: str,
    prompt_version: int = 1,
    daily_tokens_used: int = 0,
    client: LLMClient | None = None,
) -> LLMInvocationResult:
    """One structured Gemini call with retry, model fallback and JSON repair. `output` is an instance of `schema`."""
    if daily_tokens_used >= settings.GEMINI_DAILY_TOKEN_BUDGET_PER_REPO:
        return LLMInvocationResult(
            output=None,
            model=None,
            error="daily token budget exceeded for repository",
        )

    llm = client or get_llm_client()
    user_prompt, trimmed = fit_prompt(user_prompt, settings.GEMINI_MAX_INPUT_TOKENS)
    if trimmed:
        log.warning("%s prompt trimmed to fit %s input tokens", purpose, settings.GEMINI_MAX_INPUT_TOKENS)
    req_hash = hashlib.sha256((system_prompt + "\n" + user_prompt).encode("utf-8")).hexdigest()[:16]
    calls: list[LLMCallRecord] = []

    models_to_try = model_order()  # primary, then one or several fallbacks

    last_error: str | None = None
    attempt = 0
    quota_models: list[str] = []  # models whose quota is gone, now or from an earlier call
    why: dict[str, str] = {}  # model -> what last went wrong with it, so the final error names every cause

    for model in models_to_try:
        if model_cooling(model):
            quota_models.append(model)
            last_error = last_error or f"{model}: quota used up, skipped until it resets"
            why[model] = "quota used up"
            continue
        for _retry in range(2):
            attempt += 1
            if attempt > 1 and settings.GEMINI_RETRY_BACKOFF_S > 0:
                # Exponential backoff with jitter between tries (a quota error never gets here).
                await asyncio.sleep(settings.GEMINI_RETRY_BACKOFF_S * (2 ** (attempt - 2)) * (0.75 + random.random() / 2))
            started = time.monotonic()
            try:
                async with _llm_slot():
                    raw = await llm.generate_json(
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_schema=schema,
                        temperature=_temperature_for_model(model),
                        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                        timeout_s=settings.GEMINI_TIMEOUT_S,
                    )
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                last_error = str(exc)
                why[model] = short_failure(last_error)
                calls.append(
                    LLMCallRecord(
                        purpose=purpose,
                        model=model,
                        attempt=attempt,
                        prompt_version=prompt_version,
                        latency_ms=latency_ms,
                        status="error",
                        error=last_error[:500],
                        request_hash=req_hash,
                    )
                )
                # Only retry once on primary/fallback; break immediately if API key is missing
                if "GEMINI_API_KEY is not set" in last_error:
                    return LLMInvocationResult(output=None, model=None, calls=calls, error=last_error)
                if is_quota_error(exc):
                    # This model's quota is gone, and retrying it cannot help. Leave it alone for as long as the API
                    # says, and move on to the next model (each model has its own quota).
                    calls[-1].status = "quota"
                    mark_quota_used(model, last_error)
                    quota_models.append(model)
                    log.warning("quota used up for %s; trying the next model", model)
                    break
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            calls.append(
                LLMCallRecord(
                    purpose=purpose,
                    model=raw.model,
                    attempt=attempt,
                    prompt_version=prompt_version,
                    input_tokens=raw.input_tokens,
                    output_tokens=raw.output_tokens,
                    thinking_tokens=raw.thinking_tokens,
                    latency_ms=latency_ms,
                    status="ok",
                    finish_reason=raw.finish_reason,
                    request_hash=req_hash,
                    response_text=raw.text,
                )
            )

            try:
                parsed = _parse_json(raw.text, schema)
                return LLMInvocationResult(output=parsed, model=raw.model, calls=calls)
            except (json.JSONDecodeError, ValidationError, ValueError) as parse_exc:
                # Attempt one JSON repair call using GEMINI_MODEL_REPAIR
                repair_started = time.monotonic()
                repair_model = settings.GEMINI_MODEL_REPAIR or model
                repair_sys = load_repair_prompt(prompt_version, schema)
                repair_user = (
                    f"Validation error:\n{parse_exc}\n\n"
                    f"Broken JSON:\n{raw.text}"
                )
                try:
                    repaired_raw = await llm.generate_json(
                        model=repair_model,
                        system_prompt=repair_sys,
                        user_prompt=repair_user,
                        response_schema=schema,
                        temperature=_temperature_for_model(repair_model),
                        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                        timeout_s=min(settings.GEMINI_TIMEOUT_S, 60),
                    )
                    repair_ms = int((time.monotonic() - repair_started) * 1000)
                    calls.append(
                        LLMCallRecord(
                            purpose="json_repair",
                            model=repaired_raw.model,
                            attempt=attempt,
                            prompt_version=prompt_version,
                            input_tokens=repaired_raw.input_tokens,
                            output_tokens=repaired_raw.output_tokens,
                            thinking_tokens=repaired_raw.thinking_tokens,
                            latency_ms=repair_ms,
                            status="ok",
                            finish_reason=repaired_raw.finish_reason,
                            request_hash=req_hash,
                            response_text=repaired_raw.text,
                        )
                    )
                    parsed = _parse_json(repaired_raw.text, schema)
                    return LLMInvocationResult(output=parsed, model=raw.model, calls=calls)
                except Exception as repair_exc:
                    repair_ms = int((time.monotonic() - repair_started) * 1000)
                    last_error = f"parse failed ({parse_exc}); repair failed ({repair_exc})"
                    why[model] = "returned invalid JSON"
                    calls.append(
                        LLMCallRecord(
                            purpose="json_repair",
                            model=repair_model,
                            attempt=attempt,
                            prompt_version=prompt_version,
                            latency_ms=repair_ms,
                            status="error",
                            error=str(repair_exc)[:500],
                            request_hash=req_hash,
                        )
                    )
                    break  # move on to fallback model

    if quota_models and len(quota_models) == len(models_to_try):  # every model is out of quota: nothing more to try today
        return LLMInvocationResult(output=None, model=None, calls=calls, error=f"quota: {last_error}"[:500], quota=True)
    return LLMInvocationResult(
        output=None,
        model=None,
        calls=calls,
        # e.g. "gemini-3.1-flash-lite: overloaded (503); gemini-3.6-flash: quota used up" rather than only the last error
        error=("; ".join(f"{m}: {w}" for m, w in why.items()) or last_error or "reasoning LLM call failed")[:500],
    )
