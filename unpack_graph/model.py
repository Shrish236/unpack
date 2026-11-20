"""Plain data model shared by extraction (pass 1), resolution (pass 2) and output."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

TIER_EXTRACTED = "EXTRACTED"
TIER_INFERRED = "INFERRED"
TIER_AMBIGUOUS = "AMBIGUOUS"
TIER_UNRESOLVED = "UNRESOLVED"
TIER_RANK = {TIER_EXTRACTED: 0, TIER_INFERRED: 1, TIER_AMBIGUOUS: 2, TIER_UNRESOLVED: 3}


@dataclass
class Shape:
    """Syntactic shape of a callee or of a value expression.

    kind: name | call | literal | other.  `base` is the identifier for kind=name
    (this includes ``self``/``cls``; the resolver decides what they mean).  `super`
    is encoded as kind=super.  `recv` is the inner call whose *result* is the
    base for kind=call (``self.f(x).g()``).  `attrs` is the attribute chain after the base.
    """
    kind: str
    base: str = ""
    attrs: tuple = ()
    recv: Optional["CallSite"] = None
    raw: str = ""
    elems: tuple = ()                # kind=coll: shapes of the container's values/elements
    inner: Optional["Shape"] = None  # kind=index: the subscripted expression

    def last(self) -> str:
        return self.attrs[-1] if self.attrs else self.base


@dataclass
class CallSite:
    line: int
    col: int
    end_line: int
    raw: str
    shape: Shape
    owner: str = ""            # function id, or module id for module-level calls
    arg_names: tuple = ()      # bare Shapes passed as arguments (function references)
    is_await: bool = False
    kwargs: tuple = ()         # keyword argument names passed at this site
    npos: int = 0              # number of positional arguments
    splat: bool = False        # *args / **kwargs expansion present
    guards: tuple = ()         # parameters whose positive test (`if p`, `p is not None`) encloses the call
    dyn: tuple = ()            # getattr(obj, name): (receiver Shape, (kind, text)) with kind literal|prefix|unknown


@dataclass
class AttrAccess:
    """A non-call attribute chain (property getter/setter candidates)."""
    line: int
    col: int
    shape: Shape               # attrs non-empty
    write: bool = False
    owner: str = ""


@dataclass
class Implicit:
    """An implicit protocol call, e.g. ``with expr as x`` -> __enter__/__exit__."""
    line: int
    col: int
    kind: str                  # with | async_with | iter | getitem | eq | bool | str | op ...
    shape: Shape               # shape of the operand expression
    is_call: bool
    owner: str = ""
    raw: str = ""
    names: tuple = ()          # dunder methods the protocol invokes
    first: bool = False        # True: use the first dunder found; False: use all found


@dataclass
class Binding:
    name: str
    kind: str                  # call | expr | with | ann | param
    shape: Optional[Shape] = None
    ann: Optional[str] = None
    line: int = 0
    is_async: bool = False     # for `with`
    index: int = 0             # for_unpack: position in the target tuple


@dataclass
class AttrBinding:
    attr: str
    kind: str                  # call | expr | ann
    shape: Optional[Shape] = None
    ann: Optional[str] = None
    line: int = 0


@dataclass
class ImportRec:
    kind: str                  # import | from
    module: str                # dotted module text ("" for `from . import x`)
    level: int
    names: list                # [(name, alias_or_None)]; for kind=import: [(dotted, alias)]
    star: bool
    context: str               # runtime | type_only | deferred
    line: int
    scope: str = ""            # owning function id when deferred ('' = module)
    try_guard: bool = False


@dataclass
class FuncInfo:
    id: str
    name: str
    qualname: str
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
    is_staticmethod: bool = False
    is_classmethod: bool = False
    is_overload: bool = False
    is_contextmanager: bool = False
    is_nested: bool = False
    decorators: list = field(default_factory=list)
    signature: str = ""
    doc: str = ""
    returns: Optional[str] = None
    params: list = field(default_factory=list)       # [(name, annotation|None, has_default)]
    first_param: Optional[str] = None
    class_id: Optional[str] = None                   # enclosing class id for methods
    parent_func: Optional[str] = None                # enclosing function id (nested)
    body_hash: str = ""
    logic_hash: str = ""
    signature_hash: str = ""
    text_hash: str = ""
    # per-scope data for pass 2
    calls: list = field(default_factory=list)
    accesses: list = field(default_factory=list)
    implicits: list = field(default_factory=list)
    bindings: list = field(default_factory=list)
    attr_bindings: list = field(default_factory=list)
    return_shapes: list = field(default_factory=list)   # value shapes of return/yield statements
    local_names: set = field(default_factory=set)
    nested_defs: dict = field(default_factory=dict)  # local name -> func/class id (nested defs)
    param_defaults: dict = field(default_factory=dict)   # parameter -> default expression text
    rebound: set = field(default_factory=set)            # names re-assigned inside the body
    fixture_autouse: bool = False
    fixture_name: Optional[str] = None
    usefixtures: list = field(default_factory=list)
    imports: list = field(default_factory=list)      # deferred ImportRec owned by this function


@dataclass
class ClassInfo:
    id: str
    name: str
    qualname: str
    path: str
    start: int
    end: int
    bases_raw: list = field(default_factory=list)
    decorators: list = field(default_factory=list)
    is_nested: bool = False
    parent_func: Optional[str] = None
    parent_class: Optional[str] = None
    attr_anns: dict = field(default_factory=dict)       # name -> annotation text
    attr_bindings: list = field(default_factory=list)   # class-level `x = Cls()`
    is_test_class: bool = False
    metaclass: Optional[str] = None
    doc: str = ""
    doc_hash: str = ""         # hash of the full (untruncated) docstring
    logic_hash: str = ""       # class-level code: attributes etc., without docstring and method bodies


@dataclass
class ModuleInfo:
    id: str                    # relative path
    path: str
    name: str                  # dotted module name
    package: str               # dotted package the module lives in
    is_test: bool
    is_init: bool = False
    partial: bool = False
    decode_errors: bool = False
    nlines: int = 0
    imports: list = field(default_factory=list)
    funcs: list = field(default_factory=list)          # FuncInfo
    classes: list = field(default_factory=list)        # ClassInfo
    calls: list = field(default_factory=list)          # module-level calls
    accesses: list = field(default_factory=list)
    implicits: list = field(default_factory=list)
    bindings: list = field(default_factory=list)       # module-level bindings
    local_names: set = field(default_factory=set)
    all_names: Optional[list] = None                   # __all__ if statically known
    typevars: dict = field(default_factory=dict)       # name -> bound text or ""
    top_defs: dict = field(default_factory=dict)       # name -> (kind 'func'|'class', id)
    logic_hash: str = ""       # tokens outside function bodies (module-level code)
    content_hash: str = ""
    error_lines: list = field(default_factory=list)
