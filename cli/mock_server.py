"""Lightweight local mock /ingest server for testing Unpack CLI end-to-end."""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class MockIngestState:
    """Thread-safe in-memory state for received ingest payloads."""

    def __init__(self, base_url: str, out_dir: Path | None = None, quiet: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.out_dir = out_dir
        self.quiet = quiet
        self._lock = threading.Lock()
        self._counter = 0
        self._seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.received: list[dict[str, Any]] = []

    def record_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
        repo = payload["repo"]
        owner = str(repo.get("owner", "unknown"))
        name = str(repo.get("name", "unknown"))
        head_sha = str(payload["head_sha"])
        branch = str(payload["branch"])
        key = (owner, name, head_sha)

        saved_path: Path | None = None
        with self._lock:
            self.received.append(payload)
            if key in self._seen:
                existing = dict(self._seen[key])
                existing["deduplicated"] = True
                return existing, None

            self._counter += 1
            push_id = self._counter
            digest = hashlib.sha256(f"{owner}/{name}@{head_sha}".encode("utf-8")).hexdigest()[:12]
            public_id = f"an_{digest}"
            response = {
                "push_id": push_id,
                "analysis": {
                    "public_id": public_id,
                    "status": "queued",
                    "url": f"{self.base_url}/a/{public_id}",
                },
                "tracking": {
                    "branch": branch,
                    "status": "waiting_for_pr",
                },
                "deduplicated": False,
            }
            self._seen[key] = response

            if self.out_dir is not None:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                saved_path = self.out_dir / f"{head_sha[:12]}.json"
                saved_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            return response, saved_path


def _make_handler(state: MockIngestState) -> type[BaseHTTPRequestHandler]:
    class MockIngestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            if not state.quiet:
                super().log_message(format, *args)

        def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": {"code": "not_found", "message": "Not found"}})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/ingest":
                self._send_json(404, {"error": {"code": "not_found", "message": "Not found"}})
                return

            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b""

            if self.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError as exc:
                    self._send_json(
                        400,
                        {"error": {"code": "bad_gzip", "message": f"Invalid gzip: {exc}"}},
                    )
                    return

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json(
                    400,
                    {"error": {"code": "bad_json", "message": f"Invalid JSON: {exc}"}},
                )
                return

            if not isinstance(payload, dict):
                self._send_json(
                    422, {"error": {"code": "invalid_payload", "message": "Expected JSON object"}}
                )
                return

            missing = [k for k in ("repo", "branch", "base_sha", "head_sha") if k not in payload]
            if missing or not isinstance(payload.get("repo"), dict):
                self._send_json(
                    422,
                    {
                        "error": {
                            "code": "validation_error",
                            "message": f"Missing required fields: {', '.join(missing) or 'repo'}",
                        }
                    },
                )
                return

            response, saved_path = state.record_payload(payload)
            if not state.quiet:
                repo = payload["repo"]
                session = payload.get("session")
                sess_info = (
                    f"{session.get('file_name')} ({len(session.get('lines', []))} lines)"
                    if isinstance(session, dict)
                    else "none"
                )
                redactions = payload.get("redactions") or {}
                saved_note = f" saved={saved_path}" if saved_path else " (deduplicated)"
                print(
                    f"[mock-server] 202 {repo.get('owner')}/{repo.get('name')} "
                    f"branch={payload['branch']} head={payload['head_sha'][:7]} "
                    f"commits={len(payload.get('commits', []))} "
                    f"files={len(payload.get('changed_files', []))} "
                    f"session={sess_info} redactions={redactions}{saved_note}",
                    flush=True,
                )
            self._send_json(202, response)

    return MockIngestHandler


def create_mock_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    out_dir: Path | None = None,
    quiet: bool = False,
) -> tuple[ThreadingHTTPServer, MockIngestState]:
    """Create a configured ThreadingHTTPServer for /ingest testing."""
    placeholder_url = f"http://{host}:{port}"
    state = MockIngestState(base_url=placeholder_url, out_dir=out_dir, quiet=quiet)
    server = ThreadingHTTPServer((host, port), _make_handler(state))
    actual_port = server.server_address[1]
    state.base_url = f"http://{host}:{actual_port}"
    return server, state


def run_mock_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    out_dir: Path | None = None,
) -> None:
    """Run the local mock /ingest server until interrupted."""
    server, state = create_mock_server(host=host, port=port, out_dir=out_dir, quiet=False)
    print(f"Unpack mock server listening on {state.base_url}/v1/ingest", flush=True)
    if out_dir is not None:
        print(f"Saving received payloads to {out_dir.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Unpack mock server.", flush=True)
    finally:
        server.server_close()
