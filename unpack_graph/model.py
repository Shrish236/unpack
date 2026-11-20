"""Data model and schema definitions for the Unpack code knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Tiers of confidence for call resolution
Tier = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS", "UNRESOLVED"]
SiteStatus = Literal["resolved", "ambiguous", "unresolved", "external", "builtin", "no_init"]
ReachLabel = Literal["direct", "reached", "reached_uncertain", "none", "test"]
ChangeKind = Literal["added", "deleted", "modified", "renamed", "moved"]


@dataclass
class Shape:
    """Syntactic shape of an expression or callee."""
    kind: str  # "name", "call", "super", "literal", "coll", "index", "other"
    base: str = ""
    attrs: list[str] = field(default_factory=list)
    recv: CallSite | None = None
    elems: list[str] = field(default_factory=list)
    inner: Shape | None = None


@dataclass
class CallSite:
    """Recorded call site in a function or module."""
    line: int
    col: int
    raw: str
    callee: Shape
    owner: str  # function id or module path
    kwargs: list[str] = field(default_factory=list)
    npos: int = 0
    splat: bool = False
    guards: list[str] = field(default_factory=list)  # parameter names guarding this call
    arg_shapes: list[Shape] = field(default_factory=list)


@dataclass
class AttrAccess:
    """Non-call attribute access (candidate for property getter/setter)."""
    line: int
    raw: str
    chain: list[str]
    owner: str
    is_write: bool = False


@dataclass
class Implicit:
    """Implicit protocol site (__enter__, __iter__, __getitem__, __bool__, etc.)."""
    line: int
    kind: str  # "with", "for", "subscript", "eq", "bool", "str", "len", "sorted"
    dunder: str  # "__enter__", "__exit__", "__iter__", etc.
    owner: str


@dataclass
class Binding:
    """Local variable binding for type inference."""
    name: str
    kind: str  # "val", "ann", "param", "with", "for", "yield", "cast"
    val: Shape | None = None
    ann: str | None = None
    line: int = 0


@dataclass
class AttrBinding:
    """Attribute binding (self.attr = ... or class-level attr = ...)."""
    target: str  # "self.foo" or "Cls.foo"
    val: Shape | None = None
    ann: str | None = None
    line: int = 0


@dataclass
class ImportRec:
    """One import record."""
    kind: str  # "import" or "from"
    module: str
    level: int  # leading dots for relative imports
    names: list[tuple[str, str | None]] = field(default_factory=list)  # (name, as_name)
    star: bool = False
    context: str = "runtime"  # "runtime", "type_only", "deferred"
    try_guard: bool = False
    owner: str | None = None


@dataclass
class FuncInfo:
    """Extracted function or method metadata."""
    id: str  # relative/path.py::Qual.Name
    qualname: str
    name: str
    path: str
    start: int
    end: int
    is_async: bool = False
    is_method: bool = False
    is_test: bool = False
    is_fixture: bool = False
    is_abstract: bool = False
    is_property: bool = False
    is_setter: bool = False
    decorators: list[str] = field(default_factory=list)
    signature: str = ""
    doc: str | None = None
    body_hash: str = ""
    logic_hash: str = ""
    signature_hash: str = ""
    params: list[dict[str, Any]] = field(default_factory=list)  # name, default, ann
    returns: str | None = None
    calls: list[CallSite] = field(default_factory=list)
    accesses: list[AttrAccess] = field(default_factory=list)
    implicits: list[Implicit] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    attr_bindings: list[AttrBinding] = field(default_factory=list)
    return_shapes: list[Shape] = field(default_factory=list)
    rebound: set[str] = field(default_factory=set)


@dataclass
class ClassInfo:
    """Extracted class metadata."""
    id: str  # relative/path.py::Qual.Name
    name: str
    qualname: str
    path: str
    start: int
    end: int
    bases_raw: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    doc: str | None = None
    doc_hash: str = ""
    logic_hash: str = ""
    bindings: list[Binding] = field(default_factory=list)
    attr_bindings: list[AttrBinding] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Extracted module metadata (result of Pass 1)."""
    id: str  # relative/path.py
    path: str
    name: str
    package: str
    is_test: bool = False
    partial: bool = False
    decode_errors: bool = False
    imports: list[ImportRec] = field(default_factory=list)
    defs: list[FuncInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    all_exports: list[str] = field(default_factory=list)
    logic_hash: str = ""
    nlines: int = 0


@dataclass
class SiteRes:
    """Result of resolving a call, property, or implicit protocol site."""
    kind: str  # "call", "property", "implicit", "ref"
    status: SiteStatus
    targets: list[tuple[str, Tier, str]] = field(default_factory=list)  # (target_id, tier, via)
    candidates: list[str] = field(default_factory=list)
    reason: str | None = None
    raw: str = ""
    line: int = 0
    owner: str = ""
    kwargs: list[str] = field(default_factory=list)
    npos: int = 0
    splat: bool = False
    guards: list[str] = field(default_factory=list)


@dataclass
class Edge:
    """Relationship between graph nodes."""
    source: str
    target: str
    kind: str  # "CALLS", "HAS_METHOD", "INHERITS", "OVERRIDES", "REACHES", "IMPORTS"
    tier: Tier | None = None
    via: str | None = None
    lines: list[int] = field(default_factory=list)
    count: int = 1
    raw: str | None = None
    candidates: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReachInfo:
    """Reachability facts computed from test suite."""
    label: ReachLabel
    count: int = 0
    min_depth: int | None = None
    path: list[str] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    unresolved_hint: int = 0


@dataclass
class ChangeItem:
    """Change detection status for a single function or class."""
    id: str
    kind: ChangeKind
    flags: list[str] = field(default_factory=list)  # "functional", "signature", "text_only"
    head_lines: list[list[int]] = field(default_factory=list)
    base_lines: list[list[int]] = field(default_factory=list)
    old_id: str | None = None
    still_called_by: list[str] = field(default_factory=list)


@dataclass
class ChangeSet:
    """Detected changes between two revisions."""
    base_rev: str
    head_rev: str
    added_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    renamed_files: list[tuple[str, str]] = field(default_factory=list)
    changed_functions: dict[str, ChangeItem] = field(default_factory=dict)
    class_changes: dict[str, ChangeItem] = field(default_factory=dict)
    module_changes: dict[str, bool] = field(default_factory=dict)
    base_graph: Any = None
    head_graph: Any = None
