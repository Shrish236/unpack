"""Neo4j graph database loader, Cypher queries, and delta synchronizer."""

from __future__ import annotations

import os
from typing import Any

from .graph import Graph
from .model import Edge

REGION_CYPHER = """
UNWIND $changed_ids AS cid
MATCH (f:Function {id: cid})
OPTIONAL MATCH (f)<-[rc:CALLS]-(caller:Function) WHERE NOT caller:Test
OPTIONAL MATCH (f)-[dc:CALLS]->(callee:Function) WHERE NOT callee:Test
OPTIONAL MATCH (cls:Class)-[:HAS_METHOD]->(f)
OPTIONAL MATCH (t:Test)-[reach:REACHES]->(f)
RETURN f,
       collect(DISTINCT caller)[0..$cap] AS callers,
       collect(DISTINCT callee)[0..$cap] AS callees,
       cls,
       collect(DISTINCT {test: t, depth: reach.depth})[0..$tests_per_node] AS tests
"""


def get_neo4j_driver(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> Any:
    """Create Neo4j driver using environment variables or defaults."""
    from neo4j import GraphDatabase

    uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = user or os.getenv("NEO4J_USER", "neo4j")
    password = password or os.getenv("NEO4J_PASSWORD", "unpackpass")
    return GraphDatabase.driver(uri, auth=(user, password))


def load_graph(driver: Any, graph: Graph, batch_size: int = 500) -> None:
    """Load an in-memory Graph into Neo4j using batched UNWIND queries."""
    with driver.session() as session:
        # Create schema constraints / indexes
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:Module) REQUIRE m.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE")

        # Load Functions
        f_rows = []
        for f in graph.functions.values():
            reach = graph.reach_info.get(f.id)
            f_rows.append({
                "id": f.id,
                "name": f.name,
                "qualname": f.qualname,
                "path": f.path,
                "start": f.start,
                "end": f.end,
                "is_async": f.is_async,
                "is_method": f.is_method,
                "is_test": f.is_test,
                "signature": f.signature,
                "body_hash": f.body_hash,
                "logic_hash": f.logic_hash,
                "test_label": reach.label if reach else "none",
                "test_count": reach.count if reach else 0,
            })
            if len(f_rows) >= batch_size:
                session.run(
                    "UNWIND $rows AS r CREATE (f:Function) SET f = r "
                    "FOREACH (_ IN CASE WHEN r.is_test THEN [1] ELSE [] END | SET f:Test)",
                    rows=f_rows,
                )
                f_rows = []
        if f_rows:
            session.run(
                "UNWIND $rows AS r CREATE (f:Function) SET f = r "
                "FOREACH (_ IN CASE WHEN r.is_test THEN [1] ELSE [] END | SET f:Test)",
                rows=f_rows,
            )

        # Load CALLS edges
        edge_rows = []
        for e in graph.edges:
            if e.kind == "CALLS":
                edge_rows.append({
                    "source": e.source,
                    "target": e.target,
                    "tier": e.tier,
                    "via": e.via,
                    "count": e.count,
                })
                if len(edge_rows) >= batch_size:
                    session.run(
                        "UNWIND $rows AS r "
                        "MATCH (s:Function {id: r.source}), (t:Function {id: r.target}) "
                        "CREATE (s)-[:CALLS {tier: r.tier, via: r.via, count: r.count}]->(t)",
                        rows=edge_rows,
                    )
                    edge_rows = []
        if edge_rows:
            session.run(
                "UNWIND $rows AS r "
                "MATCH (s:Function {id: r.source}), (t:Function {id: r.target}) "
                "CREATE (s)-[:CALLS {tier: r.tier, via: r.via, count: r.count}]->(t)",
                rows=edge_rows,
            )
