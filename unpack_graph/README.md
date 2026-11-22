# unpack_graph

The code knowledge graph library behind Unpack, with its own CLI. It parses a Python repository, resolves calls across the whole repository, labels which functions tests reach, and works out which functions a change touched.

```bash
unpack-graph build .                          # call graph with a confidence tier per edge, plus reachability labels
unpack-graph changed . main feature-branch    # functions added, deleted, modified or renamed between two revisions
unpack-graph region . main feature-branch --out region.json   # the GraphView JSON for the change
```

## How it works

1. **Pass 1, extract** (`extract.py`): tree-sitter parses every `.py` file into functions, classes and call sites, with stable hashes. `unpack-graph extract . --check-ast` checks every definition against Python's own `ast`.
2. **Pass 2, resolve** (`resolve.py`): imports, receiver types and dispatch are resolved across the repository. Every edge carries a tier: `EXTRACTED` (read directly), `INFERRED` (resolved from types or imports) or `AMBIGUOUS` (several candidates). Calls that cannot be resolved are kept on their function with the reason instead of becoming edges.
3. **Reachability** (`reach.py`): a breadth-first search from each test, gated on arguments. Each function gets `direct`, `reached`, `reached_uncertain` or `none`. Only `none` is a red flag.
4. **Change detection** (`diff.py`): built from git objects, without touching the working tree. Changes are classified as text only, signature or behaviour.
5. **Region** (`region.py`): the changed functions, their neighbours, parent classes and the tests that reach them, in the shape of [`schemas/graphview.schema.json`](../schemas/graphview.schema.json).

`incremental.py` updates a graph for a new commit and gives the same result as a full rebuild.

## Checking the reachability labels

```bash
unpack-graph eval .                                   # measurements
coverage run -m pytest && coverage json -o cov.json   # from the repository root
unpack-graph coverage-check . cov.json                # exits 1 on any false "none"
```

## Neo4j (optional)

`neo4j_io.py` loads a graph into Neo4j and answers the region query in Cypher. The Unpack server does not use it. Connection settings: `UNPACK_NEO4J_URI`, `UNPACK_NEO4J_USER`, `UNPACK_NEO4J_PASSWORD` (defaults: `bolt://localhost:7687`, `neo4j`, `unpackpass`). The Neo4j tests are skipped when no service is running.

## Limits

Python only. Dynamic dispatch the parser cannot see is reported as unresolved rather than guessed.

Design, validation and how to adapt it to another repository: [docs/graph-design.md](../docs/graph-design.md). Query shapes: [docs/graph-api.md](../docs/graph-api.md).
