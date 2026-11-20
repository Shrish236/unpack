"""Optional pre-pass: the model looks things up in the code graph, then writes notes for the main prompt.

The notes are plain text and are context only. The structured answer (reasons, decisions) is still produced by
the schema-bound call, and its evidence is still checked against the session, so a wrong note cannot become a claim.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import settings
from .client import LLMCallRecord, LLMBackendError, get_llm_client
from .graph_context import GraphTools

log = logging.getLogger("unpack.llm")

SYSTEM = (
    "You prepare notes for a reviewer of an AI-written code change. You may call the tools to look up the code graph "
    "(callers, callees, source, tests). Look up each changed function, then write at most 12 short bullet notes: "
    "who depends on it, what it depends on, whether tests reach it, and anything surprising about how it is used. "
    "State only what the tool results show. Do not guess about intent and do not review the code style. Use at most about 10 lookups, then write the notes."
)


async def graph_notes(
    tools: GraphTools, *, changed: list[str], task: str, client: Any | None = None,
) -> tuple[str | None, list[LLMCallRecord]]:
    """Returns (notes, call records). Notes are None when tools are off, unsupported, or the call failed."""
    llm = client or get_llm_client()
    if not settings.LLM_GRAPH_TOOLS or not changed or not hasattr(llm, "generate_text_with_tools"):
        return None, []
    user = "Task given to the agent:\n" + task[:1500] + "\n\nChanged functions (ids for the tools):\n" + "\n".join(changed[:15])
    model = settings.GEMINI_MODEL_PRIMARY
    started = time.monotonic()
    try:
        raw = await llm.generate_text_with_tools(
            model=model, system_prompt=SYSTEM, user_prompt=user, tools=tools.as_tools(),
            max_calls=settings.GRAPH_TOOLS_MAX_CALLS, timeout_s=settings.GEMINI_TIMEOUT_S,
        )
    except (LLMBackendError, Exception) as exc:  # notes are optional
        log.warning("graph notes unavailable: %s", exc)
        return None, [LLMCallRecord(
            purpose="graph_notes", model=model, attempt=1, prompt_version=settings.PROMPT_VERSION,
            latency_ms=int((time.monotonic() - started) * 1000), status="error", error=str(exc)[:500],
        )]
    record = LLMCallRecord(
        purpose="graph_notes", model=raw.model, attempt=1, prompt_version=settings.PROMPT_VERSION,
        input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
        latency_ms=int((time.monotonic() - started) * 1000), response_text=raw.text[:4000],
    )
    notes = raw.text.strip()
    return (notes[:3000] or None), [record]
