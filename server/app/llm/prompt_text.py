"""Loads the prompt files and fills in the one thing a person must not type by hand: the JSON Schema.

Each prompt names its response model and puts `{{JSON_SCHEMA}}` where the schema belongs. The schema is generated from the
same pydantic model that parses the answer, so what the model is told to write and what the server accepts cannot drift
apart. Older prompt files without the placeholder load unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PLACEHOLDER = "{{JSON_SCHEMA}}"

REASONS_VERSION = 3
DECISIONS_VERSION = 4
FLOW_VERSION = 2
REPAIR_VERSION = 2


def response_models() -> dict[str, type]:
    from .client import LLMDecisionOutput, LLMFlowOutput, LLMReasoningOutput  # imported late: client imports this module's users

    return {"reasons": LLMReasoningOutput, "decisions": LLMDecisionOutput, "flow": LLMFlowOutput}


def schema_text(model: type) -> str:
    """The model's JSON Schema, compact (it costs tokens on every call)."""
    return json.dumps(model.model_json_schema(), separators=(",", ":"), ensure_ascii=False)


def render(filename: str, model: type | None = None) -> str:
    text = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    if PLACEHOLDER in text:
        if model is None:
            raise ValueError(f"{filename} has {PLACEHOLDER} but no response model was given")
        text = text.replace(PLACEHOLDER, schema_text(model))
    return text


def reasons_prompt(version: int = REASONS_VERSION) -> str:
    return render(f"reasons_v{version}.md", response_models()["reasons"])


def decisions_prompt(version: int = DECISIONS_VERSION) -> str:
    return render(f"decisions_v{version}.md", response_models()["decisions"])


def flow_prompt(version: int = FLOW_VERSION) -> str:
    return render(f"flow_v{version}.md", response_models()["flow"])


def repair_prompt(model: type | None) -> str:
    return render(f"json_repair_v{REPAIR_VERSION}.md", model)


def labels_line(labels: list[str]) -> str:
    return ", ".join(labels) if labels else "(none)"


def response_section(lines: list[str]) -> str:
    """The closing `## RESPONSE` block of a user prompt. It comes last so it is the freshest thing the model reads."""
    return "## RESPONSE\n" + "\n".join(lines)


def example_blocks(text: str) -> list[Any]:
    """Every ```json block in a prompt that parses as JSON. The tests validate them against the response models."""
    import re

    out = []
    for block in re.findall(r"```json\n(.*?)```", text, re.S):
        if PLACEHOLDER in block:
            continue
        try:
            out.append(json.loads(block))
        except ValueError:
            out.append(block)  # reported by the test as not JSON
    return out
