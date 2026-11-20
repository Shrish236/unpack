# Code knowledge graph: design

This document describes the code knowledge graph in `unpack_graph/`: what it computes, how it works, the decisions behind it, and how it is validated. It applies to any Python repository, and the validation numbers quoted here come from httpx 0.28.1, flask and requests.

## 1. Purpose

For a Python repository, the graph answers four questions:

1. **What calls what?** A call graph with a confidence tier on every edge.
2. **Which tests reach which functions?** A label per production function: `direct`, `reached`, `reached_uncertain` or `none`. `none` (no test can reach the function) is the only red flag, so it must be trustworthy.
3. **What changed between two revisions?** Each changed function is classified as added, deleted, modified (text only, signature, or behaviour), renamed or moved.
4. **What is the region around a change?** The changed functions, their immediate neighbours, the tests that reach them, and the ghosts of deleted functions, as the `GraphView` JSON that the rest of Unpack consumes.

The graph is meant to be **correct and honest**. Nothing is guessed silently: every edge says how it was found, and every call the resolver cannot place is kept with its reason.

## 2. Architecture

```
source (working tree, or a git revision read without checkout)
   │  list_files(), read(path)
   ▼
PASS 1  extract.py   one file at a time, tree-sitter
        → ModuleInfo: definitions, imports, call sites, bindings, guards, hashes
   │
   ▼
PASS 2  resolve.py   the whole repository
        → SiteRes per call / attribute access / protocol use, with status and targets
   │
   ▼
graph.py             CALLS, INHERITS, OVERRIDES, IMPORTS edges; unresolved lists
   │
   ▼
reach.py             test reachability: BFS from every test, argument-gated, depth ≤ 12
   │
   ├── diff.py       change set between two revisions (both graphs built from git objects)
   │     │
   │     ▼
   ├── region.py     GraphView JSON around the change (in memory)
   │
   └── neo4j_io.py   load into Neo4j; region as one Cypher query; delta updates
         │
         ▼
incremental.py       re-resolve only the files a change can affect
evaluate.py          measurements: coverage against ast, resolution statistics, coverage check
```

Pass 1 never looks at another file. Everything that needs cross-file knowledge, such as what `httpx.Client` is or which methods override which, happens in pass 2. This is what makes incremental updates possible: an unchanged file keeps its extraction, and its resolved sites are reused when no change can affect them.

## 3. Parsers and tools

| Tool | Use | Why |
|---|---|---|
| tree-sitter 0.25+ with tree-sitter-python | Pass 1 parse | Partial trees on files with syntax errors; exact byte offsets; every token is available for hashing |
| `ast` (standard library) | Parsing annotation text in pass 2; the ground truth for extraction | Exact for small expressions such as `Optional[X] \| None`; the reference for "every definition was found" |
| git plumbing (`ls-tree`, `cat-file --batch`, `diff --name-status -M`, `diff -U0 -M`) | Source of revisions; change sets | Revisions are read from git objects, with no checkout |
| neo4j 5 driver | Loader, region query, delta | Batched `UNWIND` writes; one Cypher statement for the region |
| jsonschema | Validating the region output in tests | The contract is `schemas/graphview.schema.json` |

The library itself needs `tree-sitter`, `tree-sitter-python` and `neo4j`. `jsonschema` is used by the tests only (it is listed among the project's dependencies in `pyproject.toml`). Jedi was evaluated as an extra resolver and was not kept: on httpx it resolved none of the 255 sites that remained unresolved.

## 4. Module map

| File | Responsibility |
|---|---|
| `model.py` | Records shared by all passes: `ModuleInfo`, `FuncInfo`, `ClassInfo`, `Shape`, `CallSite`, `Binding`, `Implicit`, `ImportRec` |
| `source.py` | `FsSource` (working tree) and `GitSource` (a revision, read through one `git cat-file --batch` process) |
| `extract.py` | Pass 1: the tree-sitter walk, definitions and hashes, module names from `__init__.py` ancestry |
| `resolve.py` | Pass 2: names, imports, classes, types, calls, properties, protocols |
| `graph.py` | `build_graph()`: assembles the graph; aggregates sites into edges |
| `reach.py` | Test reachability and labels |
| `diff.py` | Change detection between two revisions |
| `region.py` | GraphView output, in memory; `to_contract()` shapes it to the schema |
| `incremental.py` | Incremental update; graph fingerprints for equality checks |
| `neo4j_io.py` | Loader, region Cypher, delta update, database fingerprint |
| `evaluate.py` | Measurements: `eval` and `coverage-check` |
| `cli.py` | The `unpack-graph` command |

## 5. Identifiers and the data model

* A **module id** is the repository-relative path: `httpx/_client.py`.
* A **function or class id** is `relative/path.py::Qual.Name`. Nested definitions use `<locals>`: `outer.<locals>.inner`.
* Duplicate names within a file get a suffix: a property setter `Class.prop#setter`, a deleter `#deleter`, any other redefinition `#2`, `#3`.
* Module names come from `__init__.py` ancestry, so `src/flask/app.py` is `flask.app`. No configuration is needed for flat, package or `src/` layouts.

### Hashes

| Hash | Built from | Used to classify |
|---|---|---|
| `body_hash` | exact body bytes | any change |
| `logic_hash` | leaf tokens, without comments, docstrings or whitespace | behaviour (`functional`) |
| `signature_hash` | name, `async`, decorators, parameters with defaults, return annotation | signature |
| `text_hash` | the full definition text | distinguishes whitespace-only edits |

String literals are hashed as whole text, so editing a string always changes `logic_hash`. Classes have their own `doc_hash` (the full docstring) and `logic_hash` (class-level code without method bodies).

## 6. Pass 1: extraction

A recursive walk over every statement, class body and function body. A walk over only the top-level statements finds about 15% of httpx's functions, because most are methods, nested, or inside `if`/`try`/`with` blocks.

What is recorded for each scope:

* **Definitions**: qualified name, flags from decorators (`property`, setters, `staticmethod`, `classmethod`, `abstractmethod`, `overload`, `contextmanager`, `pytest.fixture` with `autouse` and `name`, `usefixtures`), parameters with annotations and default text, return annotation, docstring.
* **Test status**: a function is a test if it is `test_*` at module level, or `test*` in a `Test*` class, in a test file (`tests/`, `test_*.py`, `*_test.py`, `conftest.py`). Fixtures are not tests; they are helpers that tests reach.
* **Imports**: relative level, module text, every name with its alias, star imports, and the context: `runtime`, `type_only` (under `TYPE_CHECKING`) or `deferred` (inside a function).
* **Call sites** with the callee's shape: `f()`, `self.m()`, `a.b.c()`, `super().m()`, `f().m()`, literal receivers. Call sites in decorators belong to the decorated function.
* **Attribute accesses** that are not calls (property candidates), with a write flag.
* **Implicit protocol sites**: `with`, `for`, subscripts, operators, comparisons, truthiness, f-strings, builtin conversions.
* **Bindings** for type inference: constructor results, annotated parameters and assignments, `with ... as`, `for` targets, tuple unpacking, `except ... as`, `typing.cast`, `yield` values, dictionary, list and tuple displays.
* **Guards**: parameters whose positive test encloses a call (`if p:`, `if p is not None:`).
* **Parse health**: `partial` when the tree has errors (with the error lines), `decode_errors` for non-UTF-8 bytes.

Tree-sitter details that mattered: annotations arrive as text and are re-parsed with `ast`; `with` and `except` items wrap their alias in `as_pattern`; a block's end includes trailing indented comments, while `ast` stops at the last statement, so the end line is taken from the last non-comment token.

## 7. Pass 2: resolution

### 7.1 Values

Expressions are evaluated to values with a tier. The entity kinds are: module, class, instance, function (bound or not), `super()`, context-manager result, sequence, mapping, items view, registry collection, `pytest.raises` result, external object, unknown, and two "known but not typable" kinds, `miss` and `opaque`. `unknown` allows the unique-name fallback; `miss` and `opaque` never do. That separation is what keeps untyped receivers from being guessed.

A value carries the weakest tier along its evaluation chain.

### 7.2 Names and imports

* **Lookup order** for a bare name: local binding, enclosing function scopes, module definition, import, builtin, unresolved. Class scope is not visible to methods, as in Python.
* **Re-exports** are followed up to three hops. A four-hop chain is deliberately not followed (tested).
* **Star imports** use `__all__` when present.
* **`try: from x import f / except ImportError: def f()`** prefers the import.
* **Stdlib-name shadowing**: a package file named `typing.py` never captures `import typing`.
* **Ancestor-directory fallback**: `from conftest import X` inside `tests/` resolves to `tests.conftest`, as pytest's import path does.

### 7.3 Types

In order of preference:

1. `self` and `cls`: the enclosing class.
2. Constructor calls, calls to functions with a return annotation, and inferred returns (from `return` and `yield`) for unannotated functions.
3. `with X() as x` and `async with`, using `__enter__` or `__aenter__`, and `@contextmanager` results.
4. Parameter annotations: `Optional`, unions, `Annotated`, string forward references, `Self`, `TypeVar` bounds.
5. Instance attributes: `self.attr` assigned in any method, class-level annotations and assignments, property return types.
6. Pytest fixtures: an unannotated test parameter takes the type returned by the visible fixture of that name.
7. Containers: `list[T]`, `dict[K, V]` with `.items()`, `.values()`, `.get()`; `for` loops; registry dictionaries of classes.
8. Idioms: enum members are instances; `response = yield x` uses the send type of `Generator[Y, S, R]`; `except (A, B) as e`; `pytest.raises(E) as info` then `info.value`.

### 7.4 Call classification

Every call site gets one status:

| Status | Meaning | Edge |
|---|---|---|
| `resolved` | the target is named or inferred | `CALLS` with tier `EXTRACTED` or `INFERRED` |
| `ambiguous` | several candidates | `CALLS` with tier `AMBIGUOUS`, one edge per candidate |
| `unresolved` | not placed; the reason is kept (`no_candidate`, `unknown_name`, `unknown_receiver`, `opaque_value`, `attr_not_found`) | none; stored on the function's `unresolved_calls` |
| `external` | the callee is outside the repository (stdlib, third-party, external base class) | none |
| `builtin` | a builtin such as `len` or `isinstance` | none (except protocol edges) |
| `no_init` | a class constructed without an `__init__` in the repository | none |

**Tiers** explain confidence. `EXTRACTED` means the source names the target and it exists. `INFERRED` means it was chosen by inference, inheritance, dispatch, container typing or a unique method name. `AMBIGUOUS` means the candidates are all kept. `via` gives the reason: `type`, `inherit:<class>`, `dispatch`, `unique_name`, `property`, `with`, `ref`, `table`, `elem`, `fixture`, `escape`, `instance_protocol`, `enum_metaclass`, and the implicit kinds such as `iter`, `getitem`, `cmp`.

### 7.5 Dispatch and fallbacks

* **Override dispatch**: a call to a base method also gets `INFERRED` edges to every override in the hierarchy (`via: dispatch`). Not for constructors, not for `super()`, and never from production code into test modules.
* **Unique-name fallback**: an untyped receiver's method name is matched against the repository's methods. One candidate gives `INFERRED` (`via: unique_name`). Several give `AMBIGUOUS`. None gives `UNRESOLVED`.
* **Builtin-name guard**: if the method name also exists on `str`, `dict`, `list` and similar types, the fallback never produces `INFERRED`, because an untyped `x.get()` is more likely `dict.get`.

### 7.6 Implicit protocol edges

These exist because a call-only graph reports functions as untested when tests do run them through protocols:

| Protocol | Edge |
|---|---|
| property read and write | getter or setter (`property`) |
| `with` / `async with` | `__enter__`/`__exit__`, `__aenter__`/`__aexit__` |
| iteration | `__iter__`/`__next__` (or async) |
| subscript | `__getitem__`, `__setitem__`, `__delitem__` |
| operators and comparisons | `__eq__`, `__lt__`, `__add__`, `__contains__` and the rest |
| truthiness | `__bool__`, else `__len__` |
| f-strings and `str`, `repr` | `__str__`, else `__repr__` |
| builtins such as `sorted` and `len` | the matching dunders; element comparison for sorted typed sequences |
| function references | `ref` edge from the function that receives the reference |
| string-keyed access | `getattr(obj, "name")`: `INFERRED` edge to that method; `getattr(obj, "prefix" + x)`: `AMBIGUOUS` edges to every method of the receiver's class starting with the prefix |
| escape | an instance handed to external code: `AMBIGUOUS` edges to its dunders, or to all its methods for private or inline adapter classes |
| instance protocol | `AMBIGUOUS` edges from a class's constructor to its own dunders |
| enum metaclass | the module to `__new__` of an enum, because the enum machinery calls it at class creation |
| decorator application | `@d` and `@d(args)` apply the decorated function at definition time: the enclosing scope calls `d` (or the closure `d(args)` returns) with the function as argument. A closure returned by a factory is a function value, even when the factory is annotated with a `typing.Callable` type |
| property read through a base | a property read on a base-class receiver also reaches the overrides in its subclasses, as method calls do |
| property read, unknown receiver | `x.name` where `x` has no known type falls back to the repository's property `name`: `INFERRED` when unique, `AMBIGUOUS` otherwise. A receiver with any known type never falls back |
| method reference | a method read without a call (`report = err.show`) is a `ref`-style edge: it can be called later |
| module `__getattr__` | a missing attribute on a module links to the module's `__getattr__` (PEP 562), via `module_getattr` |

## 8. Test reachability

`reach.compute_reach()` runs a breadth-first search for every test, over `CALLS` edges with tiers `EXTRACTED` and `INFERRED`, up to depth 12. For each production function it records the count of reaching tests, the minimum depth and one shortest path.

### 8.1 Starting points

Each test starts from:

1. itself;
2. its fixtures: by parameter name, `usefixtures`, autouse fixtures, the `conftest.py` chain, transitively;
3. the module-level code of every module it imports (run at import time), including the `conftest.py` chain and the parent package `__init__`.

### 8.2 Labels

| Label | Meaning |
|---|---|
| `direct` | a test calls it (depth 1) |
| `reached` | a test reaches it at depth 2 to 12 |
| `reached_uncertain` | reachable only through an `AMBIGUOUS` edge |
| `none` | no path, even through ambiguous edges |
| `test` | the function is itself a test |

### 8.3 Depth

The default cap is 12. A cap of 8 gave false `none` labels on httpx test subsets: from a test that only calls `httpx.get`, `Response.__init__` is nine hops away. Raising the cap from 8 to 12 removed them, and a higher cap costs little in over-approximation.

### 8.4 Argument gating

A call inside `if p:` or `if p is not None:`, where `p` is a parameter with a falsy default that the body never reassigns, is followed only when the incoming call supplies `p`: by keyword, by position, or through `*args`/`**kwargs` (unknown, counted as supplied). Everything else stays reachable.

This matters for a common pattern: a new option threaded through `send(..., source=None)` into a helper called only `if source is not None:`. Without gating, every test that calls `send` would make the helper look reached. With gating, only tests that pass `source` reach it.

### 8.5 What `reached` does not claim

`reached` means a test can reach the call site on a static path. It does not mean the branch runs. On httpx test subsets, about a third of statically reached functions never executed. Use `coverage-check` (section 11) to measure how often that happens for a repository.

## 9. Change detection and the region

### 9.1 `diff.detect_changes(root, base, head)`

1. `git diff --name-status -M` gives the file status.
2. Both revisions are built from git objects, and functions are matched by id.
3. New id: `added`. Missing id: `deleted`, kept as a ghost with the callers that still reference it.
4. Same id, different hashes: `modified` with flags `text_only`, `signature` and/or `functional`.
5. Renamed files match functions by qualified name, giving `moved`.
6. A deleted and an added function with the same logic in the same file are a `renamed` pair, and in different files a `moved` pair. A rename combined with an edit is shown as delete plus add.
7. Changed line ranges come from `git diff -U0`.
8. Classes are classified the same way: bases or decorators (`signature`), class-level code (`functional`), docstring only (`text_only`).

### 9.2 The region

`region.build_region(changes, cap, tests_per_node)` returns:

* `changed` nodes for changed functions;
* `neighbor` nodes for one-hop callers and callees (production code, ranked by tier then by test count, capped), overrides and overriders;
* `container` nodes for the parent class and its base classes;
* `ghost` nodes for deleted functions, with `CALLS` edges from the callers that remain;
* `test` nodes for the tests that reach each changed function. Tests in files touched by the change come first.

Edges have `kind` (`CALLS`, `HAS_METHOD`, `INHERITS`, `OVERRIDES`, `REACHES`), `tier`, `via`, `lines`, `candidates` and an `id`. Every node has `props`, `change` (kind, flags, line ranges, old id, still-called-by) and `tests` (label, count, minimum depth, path, test list, unresolved hint). The finer internal role is kept as `relation`.

The output is validated against `schemas/graphview.schema.json`. `meta.module_changes`, `meta.class_changes` and `meta.unresolved_calls` are objects keyed by path, class id and function id.

## 10. Neo4j

### 10.1 Schema

`Module`, `Class` and `Function` nodes (with `:Test` on test functions and `:Ghost` on deleted functions). Relationships: `CONTAINS`, `HAS_METHOD`, `INHERITS`, `OVERRIDES`, `IMPORTS`, `CALLS` (with the same properties as the in-memory edge) and `REACHES` (with depth, path and whether it is uncertain). Indexes on `id`, `path` and `name`. All writes are `UNWIND` batches of 500.

### 10.2 Region query

`REGION_CYPHER` answers a region in one statement. For each changed id it selects callers, callees, parent and base classes, overrides and overriders, and tests, each with tier ranking, test count and caps. Python only reshapes the rows. The result is the same as the in-memory builder's; a test checks this, and the CLI was checked on five real changes.

### 10.3 Delta update

`graph_rows()` gives keyed rows for every node and relationship of a graph. `apply_delta()` deletes what vanished, updates what changed and creates what is new. `db_signature()` is an order-independent fingerprint of the stored graph, so a delta can be compared with a full load.

## 11. Incremental update

`incremental.update_graph(old, source, changed, deleted)` re-extracts the changed files and re-resolves only the files a change can affect:

* the changed and deleted files;
* their importers, two hops out, using the import edges of both the old and the new graph;
* the files that define ancestors of changed classes (override dispatch reaches the changed subclasses);
* files whose name-fallback sites mention a method name whose definitions appeared, disappeared or changed in number.

Every other file keeps its resolved sites. Reachability is recomputed. `graph_fingerprint()` and `diff_fingerprints()` compare a result with a full rebuild. The incremental result matched a full rebuild on 12 consecutive httpx commits and on every scenario in `tests/test_incremental.py`.

On a repository where one module is imported by most others, most files are affected, and the saving is small. The update is exact either way. Files whose getattr dispatch depends on a method name are re-resolved when that name appears or disappears; the update stats list the affected files.

## 12. Commands

```bash
unpack-graph extract  <repo> [--rev REV] [--check-ast] [--list]   # pass 1 only
unpack-graph build    <repo> [--rev REV] [--neo4j]                # passes 1, 2 and reachability
unpack-graph changed  <repo> <base> <head> [--json]               # classified changes
unpack-graph region   <repo> <base> <head> [--cap N] [--tests-per-node N] [--out FILE] [--neo4j]
unpack-graph eval     <repo> [--json FILE]                        # measurements (exit 1 on mismatch)
unpack-graph coverage-check <repo> <coverage.json> [--json FILE]  # exit 1 on any false none
```

Neo4j connection: `UNPACK_NEO4J_URI` (default `bolt://localhost:7687`), `UNPACK_NEO4J_USER` (default `neo4j`), `UNPACK_NEO4J_PASSWORD`. The repository's `docker-compose.yml` provides the service.

Library use:

```python
from unpack_graph.graph import build_graph
from unpack_graph.source import FsSource, GitSource
from unpack_graph.diff import detect_changes
from unpack_graph.region import build_region

g = build_graph(FsSource("path/to/repo"))            # or GitSource(repo, "v1.2.3")
cs = detect_changes("path/to/repo", "main~1", "main")
view = build_region(cs)                              # the GraphView dict
```

## 13. Validation

| Property | How it is checked | Result |
|---|---|---|
| Pass 1 finds every definition | `ast.walk` over every file, comparing `(start, end, name)` | httpx 0.28.1: 1,241 of 1,241. flask: 1,622 of 1,622. requests: 807 of 807 |
| Call resolution is sound | 60 hand-labelled call sites from httpx, and an independent audit of 30 more | 27 of 28 correct on the labelled set before tuning, 28 of 28 after; 30 of 30 on the audit |
| No false `none` | a coverage.py run of httpx's own test suite (`coverage-check`) | 0 false `none` over 436 functions |
| No false `none` on subsets | 8 subsets of httpx's tests, each run under coverage, compared with labels built from that subset | 1 false `none` in 875 labels; the cause is a format-string attribute read, which static analysis cannot see |
| Gap fixes change labels only where they should | labels before and after the decorator, property and method-reference fixes | httpx: no label changes. flask: no function moved to `none`; `none` count fell (production 190 to 166). requests: production `none` 54 to 31 |
| Coverage check on `pallets/click` (2,628 tests passing under coverage, 86% of `src/`) | `coverage-check` before and after the gap fixes | false `none` 55 to 29; `none` precision 0.43 to 0.55. The 29 that remain are stdlib and framework callbacks (limit 3a) |
| Coverage check on this repository | `coverage-check` against its own test run | 4 false `none`, all in the mock ingest server's stdlib hook callbacks (limit 3a); precision 0.90 |
| Six repositories, 15 recent commits each | `ast` agreement, incremental against full rebuild, schema validation, Neo4j against memory | 100% on every check: httpx, requests, flask, click, attrs, and this repository |
| Neo4j matches memory | Cypher region and in-memory region on real changes | identical |
| Incremental matches a full rebuild | 12 consecutive httpx commits and 8 scenarios | identical fingerprints |

The unit tests (`pytest`) cover every corner in the fixtures under `tests/fixtures/`: nested and decorated definitions, every import form, re-exports, inheritance and `super()`, type inference forms, dispatch, ambiguity, containers, enums, yield and except bindings, argument gating, import-time code, change classification, region schema validation, Neo4j parity and delta, and incremental equivalence.

Performance on httpx (60 files, one process): a full build takes about 1.3 s; loading into Neo4j about 8 s, of which about 6 s writes the 107,691 `REACHES` relationships; a region query 40 ms to 70 ms.

## 14. Limits

1. `reached` is a static claim: it does not mean a test runs the code. Only `none` is a strong statement, and even it is static.
2. Calls made by third-party code (a framework calling back into the repository, a test client driving an application) are invisible. This is the main risk on framework-heavy repositories, where many production functions may be labelled `none` for that reason.
3. Dynamic dispatch is resolved only where the name is a literal or a literal prefix, for `getattr` on a name or attribute receiver. Other dynamic dispatch (registries keyed by computed strings outside dictionary literals, `functools.partial`) stays unresolved.
3a. Callbacks that a framework or the standard library calls on an object the repository handed over are invisible. Examples measured on `pallets/click`: `http.server` handlers (`do_POST`) of a class that subclasses a standard-library class, `textwrap.TextWrapper._wrap_chunks`, `pickle` and `repr` hooks on objects the stdlib receives, and callbacks stored in attributes and invoked later (`version_option`'s `callback`). The coverage check reports these as false `none` labels; the design cannot close them statically in general.
3b. An attribute on a value whose annotation names an external supertype (for example `BaseException`) is treated as external, even when the actual value is a repository subclass.
4. Type inference uses annotations, constructors, returns and a fixed set of idioms. There is no general flow-sensitive inference and no generics beyond the common containers.
5. Argument gating recognises only positive guards on parameters with falsy defaults. Other guard shapes stay reachable.
6. Re-export chains stop at three hops.
7. Renames are detected only for identical logic; a rename with an edit shows as delete plus add.
8. Duplicate module names in different directories can collide, since the first one wins.
9. Test detection follows pytest naming. `unittest.TestCase` methods outside a `Test*` class are not detected as tests.
10. Pass 1 handles `.py` files only.

## 15. Adapting to another repository

The pipeline reads the repository itself, so there is no configuration to write for a standard layout. The points that are repository-specific:

* **Skipped directories**: `source.IGNORE_DIRS`.
* **Test conventions**: `extract.is_test_path()` and the fixture and decorator names in `extract.py` (`FIXTURE_DECOS`, `PROPERTY_DECOS`, and so on).
* **Typing heuristics**: `resolve.BUILTIN_METHOD_NAMES`, `SEQ_NAMES`, `MAP_NAMES`, `ENUM_BASES`.
* **Framework entry points**: functions called by a framework rather than by repository code (route handlers, command callbacks, plugin hooks). Until these are declared, they show as `none` if no test calls them directly. This is the first thing to check on a framework repository.

A workflow for a new repository:

1. `unpack-graph eval <repo>`: pass 1 must match `ast` (exit 0). Read the unresolved reasons and the `none` list.
2. Group the `none` functions by name and path. A cluster of related names (all views, all commands, all hooks) points to a framework entry point.
3. Run the repository's tests under coverage in its own environment: `coverage run -m pytest` then `coverage json -o cov.json`, from the repository root.
4. `unpack-graph coverage-check <repo> cov.json`. The acceptance bar is zero false `none`.
5. Record the result separately for the in-sample and out-of-sample checks.

Before this procedure, the repositories checked were: httpx (all checks above), flask and requests (pass 1 and the call-graph statistics only). The flask result is the main open question: 190 production functions are labelled `none`, most likely because the test client calls into Flask from outside the repository. That is unverified until step 3 has been run for flask.

## 16. Decisions

| Decision | Reason |
|---|---|
| tree-sitter for the walk, `ast` for annotations and as the oracle | Partial trees and exact tokens, with `ast` as the independent check |
| Two passes | Pass 1 can be re-run per file; incremental updates depend on it |
| Tier = weakest tier along a chain | One rule explains every edge's confidence |
| Separate unknown, missing and opaque values | Untyped receivers are never guessed from a typed class |
| Builtin-name guard on the unique-name fallback | `x.get()` on an untyped `x` is usually `dict.get` |
| Unresolved calls stored on the function, not as nodes | Nothing is dropped, and the graph stays small |
| Separate `external`, `builtin`, `no_init` statuses | Calls into the standard library are not resolver failures |
| Protocol and escape edges are included | Without them, tests that run functions through protocols would be missed |
| Instance-protocol and escape edges are `AMBIGUOUS` | They may run, but this cannot be proven statically |
| Reachability depth 12 | Measured against coverage: 8 gave false `none` |
| Name-keyed dispatch is resolved | Running the repository's own tests under coverage found 51 false `none` in a visitor that dispatches with `getattr` |
| Decorators run in the enclosing scope | Measured on `pallets/click`: applying decorators inside the decorated function's scope left every decorator closure unreached |
| Property reads and method references count | Measured on `pallets/click`: property reads on untyped receivers, base-class properties, and methods passed around by name were all missing edges |
| Argument gating | Needed for a new option threaded through an existing method |
| Region in memory and in Cypher, tested for parity | The Cypher query is the one served; the Python version is the reference |
| Delta update by diffing keyed rows | Exact, and independent of the change that caused it |
| Jedi not kept | It resolved none of the sites the resolver left open |
| `none` is the only red flag; `reached` is never presented as executed | Static reachability over-approximates by about a third |
| Region output follows the existing schema | The schema is the repository's contract; the internal roles are kept as `relation` |
