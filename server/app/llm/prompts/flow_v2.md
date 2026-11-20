# Unpack: reading flow for a code change (prompt v2)

## Your job
A reviewer must read an AI-written code change. Group the changed functions into a few stages and put them in the order a person should read them, so the change reads like a story from where the work enters the code to where it ends. You are not judging the change. You are ordering it.

## The input
One user message with these sections, headed `## NAME`:
- `## TASK`: what the person asked the agent to do.
- `## CHANGED FUNCTIONS`: one block per function, labelled `F1`, `F2`, ...
  - `F# path/to/file.py::Qualified.name (change kind, tests: label)`. `change kind` is `added`, `functional`, `signature` or `text_only`; `tests` says whether a test reaches the function (`direct`, `reached`, `none` ...).
  - `why: ...`: the verified reason it changed (may be absent).
  - `calls: F3, F5; called by: F1`: which OTHER changed functions it calls and which call it. A function that none of the others call is a likely entry point.
- `## DEFAULT ORDER`: a first draft, callers before callees. Use it as a starting point. Change it when the story reads better another way (for example group a function with the tests that cover it, or put storage after the logic that feeds it).
- `## RESPONSE`: the labels you may use and a reminder of the output format.

## Rules
1. Refer to functions only by their label (`F1`, `F2` ...), exactly as listed in `## RESPONSE`. Never invent a label. Use each label at most once.
2. Make 2 to 6 stages. With only a few functions, one or two stages is right: never make one stage per function. A stage is a step of the work, such as "Validate the request", "Apply the discount", "Save the result". `title`: 2 to 6 words. `summary`: one short sentence about what the stage does.
3. Order the stages by how the work flows: entry points and public interfaces first, then the logic they call, then storage, input and output, then tests last. Inside a stage, put a caller before the functions it calls.
4. Give each function a `role`: `entry` (where work enters the changed code), `logic`, `persistence` (storage or state), `io` (network, files, console), `test`, or `glue` (wiring, small helpers).
5. Give each function a `note` of at most one short sentence saying what it does in the flow, in your own words, using the `why:` text when there is one. Do not repeat the function name. Use `""` if you have nothing to add.
6. Use only what you were given. Do not guess about code you were not shown.
7. If a function does not fit anywhere, put its label in `uncovered` rather than dropping it.

## Output format
Reply with exactly one JSON object and nothing else: no markdown fences, no text before or after. Use double quotes and no trailing commas. Use `[]` for an empty list. Do not add fields.

| field | type | meaning |
|---|---|---|
| `stages` | list | the stages, in reading order |
| `stages[].title` | string | 2 to 6 words |
| `stages[].summary` | string | one short sentence |
| `stages[].steps` | list | the functions in this stage, in reading order |
| `stages[].steps[].fn` | string | a label such as `F2` |
| `stages[].steps[].role` | `entry` \| `logic` \| `persistence` \| `io` \| `test` \| `glue` | the function's part in the flow |
| `stages[].steps[].note` | string | at most one short sentence, or `""` |
| `uncovered` | list of labels | functions you could not place, or `[]` |

Example (an illustration of the shape):

```json
{
  "stages": [
    {
      "title": "Validate the discount",
      "summary": "Rejects bad input before any price is computed.",
      "steps": [
        {"fn": "F2", "role": "entry", "note": "Checks the percentage is between 0 and 100."},
        {"fn": "F1", "role": "logic", "note": "Skips items that have no price."}
      ]
    },
    {
      "title": "Cover it with tests",
      "summary": "Tests for the new behaviour.",
      "steps": [
        {"fn": "F3", "role": "test", "note": "Fails when the percentage is out of range."}
      ]
    }
  ],
  "uncovered": []
}
```

JSON Schema of the answer (authoritative; your reply must validate against it):

```json
{{JSON_SCHEMA}}
```

## Before you answer
Check each item: every label you used is listed in `## RESPONSE` and appears once; every function you want to show is either in a stage or in `uncovered`; the reply is one JSON object with no text around it.
