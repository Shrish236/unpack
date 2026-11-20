"""Exports Pydantic models from server.app.schemas.api to JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from server.app.schemas.api import (
    AnalysisResponse,
    CodebaseMapResponse,
    IngestPayload,
    IngestResponse,
    NodeDetailResponse,
    NodeEdgesResponse,
    TurnsResponse,
)

SCHEMA_DIR = root_dir / "contract" / "schema"
SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

SCHEMAS = {
    "analysis_response.json": AnalysisResponse,
    "ingest_payload.json": IngestPayload,
    "ingest_response.json": IngestResponse,
    "turns_response.json": TurnsResponse,
    "node_detail_response.json": NodeDetailResponse,
    "codebase_map_response.json": CodebaseMapResponse,
    "node_edges_response.json": NodeEdgesResponse,
}


def main():
    print(f"Exporting {len(SCHEMAS)} JSON schemas to {SCHEMA_DIR}...")
    for filename, model in SCHEMAS.items():
        out_path = SCHEMA_DIR / filename
        schema = model.model_json_schema()
        out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"  ✓ Exported {filename}")
    print("Export complete.")


if __name__ == "__main__":
    main()
