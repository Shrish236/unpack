"""The code graph as LLM input.

Two ways in, both read-only and both built from the head graph the analysis already made:

1. `build_code_context` writes a CODE CONTEXT section for the prompt: for each changed function, its
   signature, who calls it, what it calls, and which tests reach it. Deterministic, no extra LLM call.
2. `GraphTools` is a small set of lookups (find, callers, callees, source, tests) that the model may call
   itself before it writes its answer, for anything the static section does not cover.

Neither is evidence. The verifier only accepts quotes from the session, so nothing here can be quoted.
"""

from __future__ import annotations

from typing import Any, Callable

MAX_LIST = 6
MAX_SOURCE_LINES = 60
MAX_RESULT_CHARS = 3000


def _usable(edge: Any) -> bool:
    return getattr(edge, "tier", None) in ("EXTRACTED", "INFERRED", "AMBIGUOUS")


def _short(fid: str) -> str:
    return fid.split("::", 1)[-1] if "::" in fid else fid


def _callers(g: Any, fid: str) -> list[str]:
    return [e.src for e in g.in_adj.get(fid, []) if "::" in e.src and e.src != fid and _usable(e)
            and e.src in g.funcs and not g.funcs[e.src].is_test]


def _callees(g: Any, fid: str) -> list[str]:
    return [e.dst for e in g.out_adj.get(fid, []) if e.dst != fid and _usable(e)
            and e.dst in g.funcs and not g.funcs[e.dst].is_test]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def describe(g: Any, fid: str) -> list[str]:
    """Plain lines about one function. Empty when the graph does not know it."""
    f = g.funcs.get(fid)
    if f is None:
        return []
    lines = [f"{f.path}:{f.start}-{f.end}  {f.signature or f.name}"]
    flags = [n for n, on in (("async", f.is_async), ("method", f.is_method), ("property", f.is_property),
                             ("test", f.is_test), ("abstract", f.is_abstract)) if on]
    if f.decorators:
        flags.append("decorators: " + ", ".join(str(d) for d in f.decorators[:3]))
    if not f.name.startswith("_") and not f.is_test:
        flags.append("public name")
    if flags:
        lines.append("  " + "; ".join(flags))
    doc = (f.doc or "").strip().splitlines()
    if doc:
        lines.append(f"  doc: {doc[0][:160]}")
    callers = _dedupe(_callers(g, fid))
    callees = _dedupe(_callees(g, fid))
    lines.append(f"  callers ({len(callers)}): " + (", ".join(_short(c) for c in callers[:MAX_LIST]) or "none")
                 + (" ..." if len(callers) > MAX_LIST else ""))
    lines.append(f"  calls ({len(callees)}): " + (", ".join(_short(c) for c in callees[:MAX_LIST]) or "none")
                 + (" ..." if len(callees) > MAX_LIST else ""))
    reach = g.reach.get(fid)
    if reach is not None:
        lines.append(f"  tests: {reach.label}" + (f" ({reach.count})" if reach.count else ""))
    return lines


def build_code_context(g: Any, node_ids: list[str], aliases: dict[str, str] | None = None) -> str:
    """The CODE CONTEXT prompt section. `aliases` maps node id to the F1, F2 label the prompt uses."""
    out = ["## CODE CONTEXT (from the code graph at the pushed commit. Context only: never quote it as evidence)"]
    any_found = False
    for nid in node_ids:
        body = describe(g, nid)
        if not body:
            continue
        any_found = True
        out.append(f"{(aliases or {}).get(nid, _short(nid))} {nid}")
        out.extend(body)
    if not any_found:
        out.append("(the graph has no entry for these functions)")
    return "\n".join(out)


class GraphTools:
    """Lookups the model can call. Every method returns short plain text and never raises.

    Each public method becomes a tool: its name, type hints and docstring are what the model sees.
    """

    def __init__(self, g: Any, read_source: Callable[[str], str | None]) -> None:
        self._g = g
        self._read = read_source
        self.calls: list[str] = []

    def _resolve(self, ref: str) -> str | None:
        ref = (ref or "").strip()
        if ref in self._g.funcs:
            return ref
        matches = [fid for fid, f in self._g.funcs.items() if f.qualname == ref or f.name == ref or fid.endswith(ref)]
        return matches[0] if len(matches) == 1 else None

    def _cap(self, text: str) -> str:
        return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "\n...[cut]"

    def find_function(self, name: str) -> str:
        """Find functions by name or qualified name, for example 'send' or 'Client.send'. Returns ids to use with the other tools."""
        self.calls.append(f"find_function({name})")
        found = [fid for fid, f in self._g.funcs.items() if name in (f.name, f.qualname) or fid.endswith(name)]
        if not found:
            return f"No function named {name}."
        return self._cap("\n".join(f"{fid}  ({self._g.funcs[fid].signature or ''})" for fid in found[:15]))

    def get_callers(self, function_id: str) -> str:
        """List the production functions that call this function, with the file each is in."""
        self.calls.append(f"get_callers({function_id})")
        fid = self._resolve(function_id)
        if fid is None:
            return f"Unknown function {function_id}. Use find_function first."
        callers = _dedupe(_callers(self._g, fid))
        return self._cap("\n".join(f"{c}  [{self._g.funcs[c].path}:{self._g.funcs[c].start}]" for c in callers[:25])
                         or "No callers found in production code.")

    def get_callees(self, function_id: str) -> str:
        """List the production functions this function calls."""
        self.calls.append(f"get_callees({function_id})")
        fid = self._resolve(function_id)
        if fid is None:
            return f"Unknown function {function_id}. Use find_function first."
        callees = _dedupe(_callees(self._g, fid))
        return self._cap("\n".join(f"{c}  [{self._g.funcs[c].path}:{self._g.funcs[c].start}]" for c in callees[:25])
                         or "Calls no other production function.")

    def get_source(self, function_id: str) -> str:
        """Return the source code of a function at the pushed commit, with line numbers."""
        self.calls.append(f"get_source({function_id})")
        fid = self._resolve(function_id)
        if fid is None:
            return f"Unknown function {function_id}. Use find_function first."
        f = self._g.funcs[fid]
        text = self._read(f.path)
        if text is None:
            return "Source is not available."
        lines = text.splitlines()[f.start - 1:f.end]
        if not lines:
            return "Source is not available."
        shown = lines[:MAX_SOURCE_LINES]
        body = "\n".join(f"{f.start + i}: {line}" for i, line in enumerate(shown))
        return self._cap(body + (f"\n...[{len(lines) - len(shown)} more lines]" if len(lines) > len(shown) else ""))

    def get_tests(self, function_id: str) -> str:
        """Say whether tests reach this function, and which test gets there first."""
        self.calls.append(f"get_tests({function_id})")
        fid = self._resolve(function_id)
        if fid is None:
            return f"Unknown function {function_id}. Use find_function first."
        reach = self._g.reach.get(fid)
        if reach is None:
            return "No test information for this function."
        first = _short(reach.path[0]) if reach.path else "n/a"
        return f"{reach.label}: {reach.count} test(s) reach it; nearest path starts at {first} (depth {reach.min_depth})."

    def as_tools(self) -> list[Callable[..., str]]:
        return [self.find_function, self.get_callers, self.get_callees, self.get_source, self.get_tests]
