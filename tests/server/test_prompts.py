"""The prompts are part of the contract with the model: what they promise must be what the code sends and accepts."""

from __future__ import annotations

import json
import re
import typing

import pytest

from server.app.llm.client import LLMDecisionOutput, LLMFlowOutput, LLMReasoningOutput, fit_prompt
from server.app.llm.prompt_text import (
    DECISIONS_VERSION, FLOW_VERSION, PLACEHOLDER, PROMPTS_DIR, REASONS_VERSION, REPAIR_VERSION, decisions_prompt,
    example_blocks, flow_prompt, reasons_prompt, render, repair_prompt, schema_text,
)

CASES = [
    ("reasons", f"reasons_v{REASONS_VERSION}.md", LLMReasoningOutput, reasons_prompt),
    ("decisions", f"decisions_v{DECISIONS_VERSION}.md", LLMDecisionOutput, decisions_prompt),
    ("flow", f"flow_v{FLOW_VERSION}.md", LLMFlowOutput, flow_prompt),
]


def literals(model: type) -> set[str]:
    """Every string a Literal field of the model (or of a model nested in it) allows."""
    found: set[str] = set()

    def walk(tp) -> None:
        origin = typing.get_origin(tp)
        if origin is typing.Literal:
            found.update(str(a) for a in typing.get_args(tp) if isinstance(a, str))
        elif origin is not None:
            for a in typing.get_args(tp):
                walk(a)
        elif isinstance(tp, type) and hasattr(tp, "model_fields"):
            for f in tp.model_fields.values():
                walk(f.annotation)

    walk(model)
    return found


@pytest.mark.parametrize("name,filename,model,loader", CASES)
def test_every_example_in_a_prompt_validates_against_its_model(name, filename, model, loader):
    raw = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    examples = example_blocks(raw)
    assert examples, f"{filename} has no JSON example"
    for ex in examples:
        assert isinstance(ex, dict), f"{filename}: an example is not valid JSON: {ex[:80]}"
        model.model_validate(ex)


@pytest.mark.parametrize("name,filename,model,loader", CASES)
def test_rendered_prompt_carries_the_models_schema_and_no_leftovers(name, filename, model, loader):
    raw = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
    assert PLACEHOLDER in raw
    text = loader()
    assert PLACEHOLDER not in text and "{{" not in text
    assert schema_text(model) in text
    # the embedded schema is the real one, and it parses
    block = re.search(r"JSON Schema of the answer[^\n]*\n\n```json\n(.*?)\n```", text, re.S).group(1)
    assert json.loads(block) == model.model_json_schema()


@pytest.mark.parametrize("name,filename,model,loader", CASES)
def test_every_allowed_value_is_named_in_the_prompt(name, filename, model, loader):
    text = loader()
    missing = [v for v in sorted(literals(model)) if f"`{v}`" not in text]
    assert not missing, f"{filename} never names {missing} in backticks"


@pytest.mark.parametrize("name,filename,model,loader", CASES)
def test_prompt_states_the_response_format(name, filename, model, loader):
    text = loader()
    for phrase in ("exactly one JSON object", "no markdown fences", "no trailing commas", "Do not add fields", "## Output format", "## Before you answer"):
        assert phrase in text, f"{filename} lacks: {phrase}"
    for field in model.model_fields:
        assert f"`{field}`" in text, f"{filename} does not describe field {field}"


def test_repair_prompt_carries_the_schema_of_the_failed_call():
    text = repair_prompt(LLMFlowOutput)
    assert schema_text(LLMFlowOutput) in text and "{{" not in text
    with pytest.raises(ValueError):
        render(f"json_repair_v{REPAIR_VERSION}.md", None)  # a repair prompt without a schema is a bug, not a default


def test_old_prompt_files_still_load_unchanged():
    assert render("reasons_v2.md") == (PROMPTS_DIR / "reasons_v2.md").read_text(encoding="utf-8")


def test_response_block_survives_a_prompt_that_had_to_be_trimmed():
    user = "## TASK\nx\n\n" + "## SESSION\n" + "line of session text\n" * 60000 + "\n## RESPONSE\nReply with one JSON object.\n"
    out, trimmed = fit_prompt(user, 20000)
    assert trimmed and out.startswith("## TASK") and out.rstrip().endswith("Reply with one JSON object.")
