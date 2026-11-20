"""Gemini API client wrapper with retries, model fallback, JSON repair, and call logging (§4.7)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
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
    output: LLMReasoningOutput | None
    model: str | None
    calls: list[LLMCallRecord] = field(default_factory=list)
    error: str | None = None


class LLMBackendError(RuntimeError):
    """Raised by an LLM backend when a request fails."""


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
            raise LLMBackendError(f"Gemini API error ({type(exc).__name__}): {exc}") from exc


_override_client: LLMClient | None = None


def set_llm_client(client: LLMClient | None) -> None:
    """Inject a fake/custom LLMClient in tests (mirrors services.set_github)."""
    global _override_client
    _override_client = client


def get_llm_client() -> LLMClient:
    if _override_client is not None:
        return _override_client
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


def _parse_reasoning_json(text: str) -> LLMReasoningOutput:
    cleaned = _strip_code_fence(text)
    obj = json.loads(cleaned)
    return LLMReasoningOutput.model_validate(obj)


async def run_reasoning_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    prompt_version: int = 1,
    daily_tokens_used: int = 0,
    client: LLMClient | None = None,
) -> LLMInvocationResult:
    """Run one structured Gemini reasoning call with retry, fallback, and JSON repair."""
    if daily_tokens_used >= settings.GEMINI_DAILY_TOKEN_BUDGET_PER_REPO:
        return LLMInvocationResult(
            output=None,
            model=None,
            error="daily token budget exceeded for repository",
        )

    llm = client or get_llm_client()
    req_hash = hashlib.sha256((system_prompt + "\n" + user_prompt).encode("utf-8")).hexdigest()[:16]
    calls: list[LLMCallRecord] = []

    models_to_try = [settings.GEMINI_MODEL_PRIMARY]
    if settings.GEMINI_MODEL_FALLBACK and settings.GEMINI_MODEL_FALLBACK not in models_to_try:
        models_to_try.append(settings.GEMINI_MODEL_FALLBACK)

    last_error: str | None = None
    attempt = 0

    for model in models_to_try:
        for _retry in range(2):
            attempt += 1
            started = time.monotonic()
            try:
                raw = await llm.generate_json(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=LLMReasoningOutput,
                    temperature=_temperature_for_model(model),
                    max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                    timeout_s=settings.GEMINI_TIMEOUT_S,
                )
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                last_error = str(exc)
                calls.append(
                    LLMCallRecord(
                        purpose="reasons",
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
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            calls.append(
                LLMCallRecord(
                    purpose="reasons",
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
                parsed = _parse_reasoning_json(raw.text)
                return LLMInvocationResult(output=parsed, model=raw.model, calls=calls)
            except (json.JSONDecodeError, ValidationError, ValueError) as parse_exc:
                # Attempt one JSON repair call using GEMINI_MODEL_REPAIR
                repair_started = time.monotonic()
                repair_model = settings.GEMINI_MODEL_REPAIR or model
                repair_sys = load_repair_prompt(prompt_version)
                repair_user = (
                    f"Validation error:\n{parse_exc}\n\n"
                    f"Broken JSON:\n{raw.text}"
                )
                try:
                    repaired_raw = await llm.generate_json(
                        model=repair_model,
                        system_prompt=repair_sys,
                        user_prompt=repair_user,
                        response_schema=LLMReasoningOutput,
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
                    parsed = _parse_reasoning_json(repaired_raw.text)
                    return LLMInvocationResult(output=parsed, model=raw.model, calls=calls)
                except Exception as repair_exc:
                    repair_ms = int((time.monotonic() - repair_started) * 1000)
                    last_error = f"parse failed ({parse_exc}); repair failed ({repair_exc})"
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

    return LLMInvocationResult(
        output=None,
        model=None,
        calls=calls,
        error=last_error or "reasoning LLM call failed",
    )
