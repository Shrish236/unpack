# Code knowledge graph: what it holds and how to query it

This document is the reference for the graph's contents and its responses. For how the graph is built, see `graph-design.md`.

Examples use output from a real run on `pallets/flask` (1,462 functions). Long lists are trimmed.

## 1. Four ways in

| Surface | Use it for | Cost |
|---|---|---|
| `unpack-graph query` (CLI) | one question about a repository, answered as JSON | one cold build per call, then microseconds |
| Python: `GraphIndex` | many questions in one process | build once, then microseconds per query |
| `unpack-graph build --neo4j` and Cypher | serving many users, or questions across changes | indexed lookups in the database (not measured here, see section 8) |
| `unpack-graph region`, `changed`, `eval`, `coverage-check` | change review, measurement | one build per call |

## 2. What the graph holds

### 2.1 Nodes

**Module** (one per `.py` file)

| Property | Meaning |
|---|---|
| `id` = `path` | repository-relative path, for example `src/flask/app.py` |
| `name` | dotted module name, for example `flask.app` (PEP 420 rules: a directory is a package when it has `__init__.py` or holds `.py` files) |
| `is_test` | the file is test code (`tests/`, `test_*.py`, `*_test.py`, `conftest.py`) |
| `partial` | the parser found errors; the definitions listed may be incomplete |
| `package` | the package the module belongs to |
| `is_init` | the file is an `__init__.py` |
| `nlines` | number of lines in the file |

**Class**

| Property | Meaning |
|---|---|
| `id` | `path::Qual.Name`, for example `src/flask/app.py::Flask` |
| `name`, `qualname`, `path` | the name, the dotted name within the file, the file |
| `start`, `end` | first and last line |
| `bases_raw`, `bases` | base expressions as written, for example `["App"]` (the resolved bases are edges, below) |
| `doc_hash`, `logic_hash` | hashes of the docstring and of class-level code (without method bodies). In memory only: the Neo4j store does not hold them |

**Function** (functions, methods, properties, closures, fixtures)

| Property | Meaning |
|---|---|
| `id` | `path::Qual.Name`. Nested definitions use `<locals>`: `test_x.<locals>.Flask`. A duplicate name gets `#2`, a property setter `#setter` |
| `name`, `qualname`, `path`, `start`, `end` | as above |
| `is_method`, `is_property`, `is_setter`, `is_staticmethod`, `is_classmethod`, `is_abstract`, `is_async`, `is_overload`, `is_contextmanager`, `is_nested` | flags from the definition |
| `is_test`, `is_fixture` | test function, or pytest fixture |
| `in_test_module` | the function is in a test file (it may still be a helper, not a test) |
| `decorators`, `signature`, `doc` | decorator names, the signature as written, the docstring |
| `body_hash`, `logic_hash`, `signature_hash` | hashes (section 2.4) |
| `test_label` | reachability label: `direct`, `reached`, `reached_uncertain`, `none`, or `test` (section 3) |
| `test_count` | number of tests that reach it on a static path |
| `test_min_depth` | shortest path length from a test (1 = a test calls it directly) |
| `test_path` | one shortest path, as a list of ids from the test to the function |
| `test_unc_count`, `test_unc_depth`, `test_unc_path` | the same, for paths through ambiguous edges only |

**Stored in Neo4j vs in memory.** The Neo4j function node carries: `id`, `name`, `qualname`, `path`, `start`, `end`, `is_async`, `is_method`, `is_test`, `is_fixture`, `is_abstract`, `is_property`, `decorators`, `signature`, `doc`, the three hashes that are in the list above, `in_test_module`, and the `test_*` properties. The flags `is_setter`, `is_staticmethod`, `is_classmethod`, `is_overload`, `is_contextmanager` and `is_nested`, the parent references, and `text_hash` are in memory only. Class hashes are in memory only too, as noted above.

Nodes carry extra labels: `:Test` on test functions, `:Ghost` on functions deleted in a change (a placeholder, so their callers can still be shown).

### 2.2 Edges

| Edge | From to | Properties |
|---|---|---|
| `CONTAINS` | Module to Class or Function; Function to Function or Class (nesting); Class to Class (nested class) | none (structure: nesting) |
| `HAS_METHOD` | Class to Function | none |
| `INHERITS` | Class to base Class, inside the repository | none |
| `OVERRIDES` | Function to the base-class method it replaces | none |
| `IMPORTS` | Module to Module | `names`, `level`, `context` (`runtime`, `type_only`, `deferred`) |
| `CALLS` | Function (or Module, for module-level code) to Function | `tier`, `via`, `line`, `lines`, `count`, `raw`, `candidates` |
| `REACHES` | Test to Function | `depth`, `path`, `uncertain` |

`CALLS` edges to a deleted function point at its `:Ghost` node.

**What `via` means on a `CALLS` edge** (how the target was found). `null` means a plain call to a name the module defines or imports. The other values:

| `via` | Meaning |
|---|---|
| `self` | a method call on `self` or `cls` |
| `inherit:<class>` | the method is inherited from `<class>` |
| `dispatch` | a call through a base-class method, reaching the subclass overrides |
| `property` | a property read (`obj.name`) |
| `unique_name` | the receiver's type is unknown; the only repository method with that name is the target |
| `ambiguous` | several repository methods share the name; all are kept in `candidates` |
| `ref` | a function passed as a value (a reference, not a call) |
| `returned` | a function returned by a factory, reached when the factory is called |
| `module_getattr` | a missing module attribute, linked to the module's `__getattr__` |
| `implicit` | a protocol call (`with`, `for`, operators, and so on) |
| `removed` | a call to a function deleted in the change (in `region` output only) |

### 2.3 Confidence tiers

| Tier | Meaning |
|---|---|
| `EXTRACTED` | the name is written directly and the target is certain |
| `INFERRED` | found through a type the tool worked out, or a unique name in the repository |
| `AMBIGUOUS` | several candidates; all of them are kept in `candidates` |
| `UNRESOLVED` | the tool could not place the call; kept on the function with a reason |

An edge takes the weakest tier along its chain.

### 2.4 Hashes

| Hash | Built from | Use |
|---|---|---|
| `body_hash` | exact body text | any change |
| `logic_hash` | tokens without comments, docstrings and whitespace | behaviour changed |
| `signature_hash` | name, `async`, decorators, parameters, return annotation | signature changed |
| `text_hash` (in memory only) | full definition text | whitespace-only edits |

## 3. Reachability labels

| Label | Meaning | Red flag? |
|---|---|---|
| `direct` | a test calls it | no |
| `reached` | a test reaches it through calls, up to depth 12 | no |
| `reached_uncertain` | reachable only through an ambiguous edge, or through machinery the graph cannot see (dunders, closures, methods of classes with an external base) | no |
| `none` | no path at all | yes: a candidate for untested or dead code |
| `test` | the function is itself a test | no |

`reached` means a test *can* reach the code on a static path. It does not mean the branch runs. Use `coverage-check` to measure this on a repository.

The default labels are the implicit-invocation policy. Run with `--strict-none` to label every function with no static path `none`.

## 4. The `query` command

```bash
unpack-graph query <repo> <op> [target] [--rev REV] [--limit N] [--include-uncertain] [--include-tests] [--strict-none] [--timing]
```

- `<repo>` is a repository root (working tree). `--rev REV` reads a git revision instead.
- `target` is a function or class id, a name, or a qualified name. If several ids match, the first is used and a note goes to stderr.
- Every op prints one JSON document to stdout.
- `--timing` prints the build, index and query times to stderr.

| Op | Target | Response |
|---|---|---|
| `find` | text | list of node summaries whose id, qualified name or name matches |
| `node` | id or name | one node: kind, location, label, test counts, unresolved count |
| `callers` | id or name | functions that call it, sorted by tier. `--include-tests` adds test callers |
| `callees` | id or name | functions it calls, sorted by tier |
| `tests` | id or name | tests that reach it, with depth. `--include-uncertain` adds ambiguous paths. `--limit` caps the list |
| `overrides` | id or name | `overrides` (methods it replaces) and `overridden_by` |
| `class` | class id or name | bases, subclasses, methods with labels |
| `unresolved` | id or name | calls the tool could not place, with line, source text and reason |
| `untested` | path prefix (optional) | production functions labelled `none`, optionally under a path prefix |

### 4.1 Examples (flask)

```bash
unpack-graph query /path/to/flask node "Scaffold.route"
```

```json
{
 "kind": "function",
 "id": "src/flask/sansio/scaffold.py::Scaffold.route",
 "name": "route",
 "qualname": "Scaffold.route",
 "path": "src/flask/sansio/scaffold.py",
 "start": 344,
 "end": 373,
 "is_test": false,
 "is_method": true,
 "is_property": false,
 "is_async": false,
 "class_id": "src/flask/sansio/scaffold.py::Scaffold",
 "signature": "def route(self, rule: str, **options: t.Any) -> t.Callable[[T_route], T_route]",
 "decorators": ["setupmethod"],
 "label": "direct",
 "reached_by": 391,
 "uncertain_reached_by": 0,
 "unresolved_sites": 0
}
```

```bash
unpack-graph query /path/to/flask tests "Scaffold.route" --limit 2
```

```json
[
 {"test": "tests/test_appctx.py::test_app_tearing_down_with_handled_exception_by_app_handler", "depth": 1, "uncertain": false},
 {"test": "tests/test_appctx.py::test_app_tearing_down_with_unhandled_exception", "depth": 1, "uncertain": false}
]
```

```bash
unpack-graph query /path/to/flask callers "Scaffold.route" --limit 3
```

```json
[
 {"id": "src/flask/sansio/scaffold.py::Scaffold._method_route", "tier": "EXTRACTED", "via": null,
  "line": 293, "lines": [293], "count": 1, "raw": "self.route(rule, methods=[method], **options)", "candidates": []},
 {"id": "examples/celery/src/task_app/__init__.py::create_app", "tier": "INFERRED",
  "via": "inherit:src/flask/sansio/scaffold.py::Scaffold", "line": 19, "lines": [19], "count": 1,
  "raw": "app.route(\"/\")", "candidates": []},
 {"id": "examples/tutorial/flaskr/__init__.py::create_app", "tier": "INFERRED",
  "via": "inherit:src/flask/sansio/scaffold.py::Scaffold", "line": 26, "lines": [26], "count": 1,
  "raw": "app.route(\"/hello\")", "candidates": []}
]
```

The second and third callers are calls through an instance of `Flask`, which inherits `route` from `Scaffold`. The `inherit:` value shows that path.

```bash
unpack-graph query /path/to/flask class Flask
```

```json
{
 "id": "src/flask/app.py::Flask",
 "name": "Flask",
 "path": "src/flask/app.py",
 "bases": ["src/flask/sansio/app.py::App"],
 "subclasses": ["src/flask/globals.py::FlaskProxy", "tests/test_config.py::test_custom_config_class.<locals>.Flask"],
 "methods": [
  {"id": "src/flask/app.py::Flask.__call__", "name": "__call__", "label": "reached_uncertain"},
  {"id": "src/flask/app.py::Flask.__init__", "name": "__init__", "label": "direct"}
 ]
}
```

The output is cut to two subclasses and two methods here; the full output lists all of them. The `Flask` name matches two ids (the class and a test-local class of the same name), so the query prints a note on stderr and uses the first.

The `overrides`, `unresolved` and `untested` responses have the shapes in section 4.2; their values depend on the repository.

### 4.2 Response shapes

| Op | Shape |
|---|---|
| `find` | `[node, ...]` |
| `node` | `{kind, id, name, qualname, path, start, end, is_test, is_method, is_property, is_async, class_id, signature, decorators, label, reached_by, uncertain_reached_by, unresolved_sites}` for a function; `{kind, id, name, qualname, path, start, end, bases, methods}` for a class |
| `callers`, `callees` | `[{id, tier, via, line, lines, count, raw, candidates}, ...]` |
| `tests` | `[{test, depth, uncertain}, ...]` |
| `overrides` | `{overrides: [id, ...], overridden_by: [id, ...]}` |
| `class` | `{id, name, path, bases, subclasses, methods: [{id, name, label}]}` |
| `unresolved` | `[{line, raw, reason}, ...]` |
| `untested` | `[id, ...]` |

Reasons in `unresolved` and in site statuses are listed in `graph-design.md` section 7.4.

## 5. Python API

```python
from unpack_graph.graph import build_graph
from unpack_graph.query import GraphIndex
from unpack_graph.source import FsSource

g = build_graph(FsSource("/path/to/repo"))   # passes 1 and 2, reachability
ix = GraphIndex(g)                            # one pass; then every method is a dictionary lookup

ix.find("Scaffold.route")                     # ids
ix.node("src/flask/sansio/scaffold.py::Scaffold.route")
ix.callers(fid, production_only=True)
ix.callees(fid)
ix.tests_for(fid, include_uncertain=False, limit=None)
ix.overrides(fid)
ix.class_info(cid)
ix.unresolved(fid)
ix.untested_in(path_prefix="", limit=None)
ix.in_path("src/flask/app.py")                # function ids defined in one file
```

The lower-level structures are on `g`: `g.funcs`, `g.classes`, `g.mods`, `g.calls` (keyed by `(caller, callee)`), `g.in_adj` and `g.out_adj` (adjacency lists of edges), `g.reach` (labels), `g.reach_pairs` (per test: function to `(depth, parent, path)`), `g.unresolved`, `g.sites` (every call site with its status).

## 6. Change responses

### 6.1 `changed`

```bash
unpack-graph changed <repo> <base-rev> <head-rev> [--json]
```

Text output lists each changed function with its kind (`added`, `modified`, `deleted`, `renamed`), its flags (`functional` for a change in logic, `[-]` for none, `signature` for a signature change), its line range in the head revision, and the lines that differ. Real output for the range `2352f16..01c409d` in this repository:

```text
2352f16..01c409d: 38 changed functions in 18 files
  added     [-] tests/fixtures/namespace/src/pkg/sub/mod.py::make  L4-5 diff:4-5
  modified  [functional] tests/helpers.py::extract_tree  L21-30 diff:25,28
  modified  [functional] tests/test_coverage_gaps.py::test_module_getattr_answers_a_missing_module_attribute  L33-38 diff:36-37
```

`--json` returns the full change set: `base`, `head`, `files` (status, old path, new path), `functions` (one object per change, with `kind`, `flags`, `head_lines`, `base_lines`, `old_id`, `still_called_by`), `classes`, and `modules`.

### 6.2 `region` (GraphView JSON)

```bash
unpack-graph region <repo> <base-rev> <head-rev> [--cap N] [--tests-per-node N] [--out FILE] [--neo4j]
```

The output is validated against `schemas/graphview.schema.json`. For the same range as above, the region has 142 nodes (38 `changed`, 96 `neighbor`, 6 `test`, 2 `container`) and 302 edges (185 `CALLS`, 103 `REACHES`, 14 `HAS_METHOD`). Trimmed real output, one changed function, one neighbour and one edge:

```json
{
 "version": "1.0",
 "meta": {"version": "1.0", "base": "2352f16", "head": "01c409d", "cap": 15, "tests_per_node": 5,
          "changed_count": 38, "module_changes": {...}, "class_changes": {...},
          "unresolved_calls": {
            "unpack_graph/extract.py::module_name_for": [
              {"line": 1214, "raw": "has_init(d)", "reason": "parameter_callable"}]}},
 "nodes": [
  {"id": "tests/helpers.py::extract_tree", "type": "Function", "role": "changed", "relation": "changed",
   "ghost": false,
   "props": {"id": "tests/helpers.py::extract_tree", "name": "extract_tree", "qualname": "extract_tree",
             "path": "tests/helpers.py", "start": 21, "end": 30, "is_test": false, "is_method": false, "...": "..."},
   "change": {"kind": "modified", "flags": ["functional"], "head_lines": [[25, 25], [28, 28]],
              "base_lines": [[25, 25], [28, 28]], "old_id": null, "still_called_by": []},
   "tests": {"label": "direct", "count": 1, "min_depth": 1,
             "path": ["tests/test_extraction.py::test_syntax_error_partial_non_utf8_empty_and_long",
                      "tests/helpers.py::extract_tree"],
             "tests": [{"id": "tests/test_extraction.py::test_syntax_error_partial_non_utf8_empty_and_long", "depth": 1}],
             "unresolved_hint": 0}},
  {"id": "unpack_graph/cli.py::_source", "type": "Function", "role": "neighbor", "relation": "callee",
   "ghost": false, "props": {"...": "..."}, "change": null,
   "tests": {"label": "none", "count": 0, "min_depth": 0, "path": [], "tests": [], "unresolved_hint": 0}}
 ],
 "edges": [
  {"id": "CALLS:tests/helpers.py::extract_tree->unpack_graph/extract.py::extract_file",
   "source": "tests/helpers.py::extract_tree", "target": "unpack_graph/extract.py::extract_file",
   "kind": "CALLS", "tier": "EXTRACTED", "via": null, "line": 29, "lines": [29], "count": 1,
   "raw": "extract_file(p, src.read(p), name, pkg)", "candidates": []}
 ]
}
```

- Node `role` is the contract role: `changed`, `neighbor` (caller or callee), `container` (parent or base class), `test`, or `ghost` (deleted function). `relation` keeps the finer internal role: `caller`, `callee`, `overridden`, `overrider`, `parent_class`, `base_class`, `test`.
- Edge `kind` is `CALLS`, `HAS_METHOD`, `INHERITS`, `OVERRIDES` or `REACHES`. Every edge has a stable `id` of the form `KIND:source->target`. A `REACHES` edge also carries `depth` and `path`.
- `meta.unresolved_calls` lists, per changed function, the calls the tool could not place, with the reason. In the example, `has_init(d)` is a call through a parameter, which the tool does not resolve.

### 6.3 `eval`

```bash
unpack-graph eval <repo> [--json FILE]
```

Prints the measurements; `--json FILE` also writes them to a file. Returns `root`, `build_s`, `timing_s`, `coverage_vs_ast` (definitions found against Python's own parser, with mismatches), `resolution` (call-site counts by status, for production code and test code), and `reachability` (label counts and the functions labelled `none`).

### 6.4 `coverage-check`

```bash
unpack-graph coverage-check <repo> <coverage.json> [--json FILE] [--strict-none]
```

Compares labels with a coverage.py run. Returns `functions_compared`, `false_none` (labelled `none` but executed), `true_none`, `none_precision`, `never_executed`, `untested_recall`, and `tested_but_never_executed`. Exit code 1 if any false `none` exists.

## 7. Neo4j

Labels: `Module`, `Class`, `Function`, with `:Test` and `:Ghost` extra labels.

Indexes (created by `ensure_schema`, in `neo4j_io.SCHEMA_STMTS`):

| Index | Serves |
|---|---|
| `Module(id)`, `Module(path)`, `Module(name)` | module lookup and import resolution |
| `Class(id)`, `Class(path)`, `Class(name)`, `Class(qualname)` | class lookup |
| `Function(id)`, `Function(path)`, `Function(name)`, `Function(qualname)` | function lookup by id, file, name, qualified name |
| `Function(path, name)` | functions by name within a file |
| `Function(test_label)` | untested or reached functions |
| `CALLS(tier)` | filtering calls by confidence |
| `REACHES(depth)` | nearest tests first |

`:Test` and `:Ghost` are labels, so a query that starts from them uses the label store.

### 7.1 Cypher examples

These are not yet run against a live server (see section 8). Each parameter is written `$name`.

```cypher
// one function by id
MATCH (f:Function {id: $id}) RETURN f;

// production callers of a function, with the confidence of each call
MATCH (c:Function)-[r:CALLS]->(f:Function {id: $id})
WHERE c.in_test_module = false
RETURN c.id AS caller, r.tier AS tier, r.via AS via, r.line AS line
ORDER BY caller;

// tests that reach a function on a static path, nearest first
MATCH (t:Test)-[r:REACHES]->(f:Function {id: $id})
WHERE r.uncertain = false
RETURN t.id AS test, r.depth AS depth
ORDER BY depth, test
LIMIT 20;

// production functions with no test path, under a path prefix
MATCH (f:Function)
WHERE f.test_label = 'none' AND f.in_test_module = false AND f.path STARTS WITH $prefix
RETURN f.id AS id ORDER BY id;

// everything a method overrides, and everything that overrides it
MATCH (m:Function {id: $id})-[:OVERRIDES]->(o:Function) RETURN o.id AS overridden;
MATCH (x:Function)-[:OVERRIDES]->(m:Function {id: $id}) RETURN x.id AS overrider;

// class hierarchy: bases and subclasses inside the repository
MATCH (c:Class {id: $id})-[:INHERITS]->(b:Class) RETURN b.id AS base;
MATCH (s:Class)-[:INHERITS]->(c:Class {id: $id}) RETURN s.id AS subclass;

// transitive callers, up to three levels
MATCH p = (c:Function)-[:CALLS*1..3]->(f:Function {id: $id})
WHERE c.in_test_module = false
RETURN DISTINCT c.id AS caller ORDER BY caller;
```

## 8. Speed

### 8.1 What was measured

Measured on this container with the in-memory index (`GraphIndex`). Each query row is over 300 real functions (or 200 names for `find`). p50 and p99 are per query, in milliseconds.

| Repo | Functions | Cold build | Index build | `node` p50 / p99 | `callers` p50 / p99 | `tests` p50 / p99 | `find` substring p50 / p99 |
|---|---|---|---|---|---|---|---|
| unpack (this repo) | 602 | 0.51 s | 3.7 ms | 0.0014 / 0.0052 | 0.0012 / 0.0101 | 0.0003 / 0.0049 | 0.044 / 0.069 |
| httpx | 1,134 | 1.81 s | 60 ms | 0.0018 / 0.0034 | 0.0009 / 0.0291 | 0.0021 / 0.0969 | 0.089 / 0.115 |
| requests | 711 | 0.69 s | 24 ms | 0.0017 / 0.0036 | 0.0006 / 0.0169 | 0.0004 / 0.0454 | 0.070 / 0.097 |
| flask | 1,462 | 0.96 s | 30 ms | 0.0016 / 0.0027 | 0.0009 / 0.0158 | 0.0004 / 0.0459 | 0.120 / 0.148 |
| click | 1,915 | 2.63 s | 82 ms | 0.0021 / 0.0057 | 0.0010 / 0.0196 | 0.0008 / 0.1379 | 0.196 / 0.302 |
| attrs | 1,150 | 1.15 s | 34 ms | 0.0018 / 0.0063 | 0.0005 / 0.0145 | 0.0004 / 0.0878 | 0.108 / 0.174 |

So a query against a loaded index takes 1 to 2 microseconds at the median, and at most 0.14 ms at p99 for an id lookup on a repository of this size. Substring search scans the names and is the slowest at 0.1 to 0.3 ms.

### 8.2 The first query

The first query pays the cold build, which is the expensive part:

- `unpack-graph query` builds the graph from source on each call: 0.5 s to 2.6 s here.
- A pickled snapshot of the built graph reloads in 0.18 s for flask and 0.45 s for click, and rebuilding the index adds 0.15 to 0.4 s. That is not milliseconds, so the snapshot is not used.

So from a cold start, the CLI answers in well under a second, not in milliseconds. Milliseconds from a cold start needs a process that stays up with the index loaded (one build, then every query is microseconds), or the Neo4j path with its indexes.

### 8.3 Neo4j timing: not measured yet

The Neo4j indexes in section 7 were added to the loader, but this session could not start a Neo4j server to test them, so their effect and the cypher queries in section 7.1 are unverified. The loader's earlier measurements, from an earlier run on httpx, were a load of about 8 s (of which about 6 s wrote 107,691 `REACHES` relationships) and region queries of 40 to 70 ms. Those numbers predate the indexes and must be re-measured.

To measure: start Neo4j (`docker compose up -d neo4j`), run `pytest tests/test_neo4j.py` (the three tests skip without a server), then `unpack-graph build <repo> --neo4j` and time the cypher queries in section 7.1 with `PROFILE`.

## 9. Limits of what is stored

- Only Python `.py` files. Other languages are out of scope.
- Calls made from outside the repository (framework callbacks, a test client driving an application, the standard library calling back) are not visible. They show as `none` or as unresolved. The coverage check measures how often.
- Dynamic dispatch is resolved only for literal or literal-prefix names.
- Classes built at run time (attrs-style builders, `type(...)`, methods installed with `setattr`) are not in the graph.
- `reached` is static: it is not evidence the code runs.
- Module names follow PEP 420 rules. A layout the rules cannot see (for example a `sys.path` hack) can give a module a different name than Python gives it.
