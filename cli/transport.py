"""Ingest payload assembly and gzipped HTTP transport for the Unpack CLI."""

from __future__ import annotations

import gzip
import json
import platform
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__


class IngestError(RuntimeError):
    """Raised when sending the ingest payload fails."""


def is_local_url(server_url: str) -> bool:
    """Return True if server_url points to localhost / loopback."""
    parsed = urllib.parse.urlparse(server_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def build_ingest_payload(
    *,
    repo: dict[str, Any],
    branch: str,
    base_sha: str,
    head_sha: str,
    commits: list[dict[str, str]],
    diff: str,
    changed_files: list[dict[str, Any]],
    session: dict[str, Any] | None,
    redactions: dict[str, int],
    hook_name: str = "pre-push",
) -> dict[str, Any]:
    """Assemble an IngestPayload dict matching contract/schema/ingest_payload.json."""
    os_name = (
        f"{platform.system().lower()}-{platform.release()}" if platform.system() else "unknown"
    )
    return {
        "schema_version": 1,
        "repo": repo,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "commits": commits,
        "diff": diff,
        "changed_files": changed_files,
        "session": session,
        "redactions": redactions,
        "client": {
            "cli_version": __version__,
            "os": os_name,
            "hook": hook_name,
        },
    }


def send_ingest_payload(
    server_url: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Gzip-compress and POST payload to {server_url}/ingest."""
    if not token and not is_local_url(server_url):
        raise IngestError(
            f"No ingest token configured for non-local server {server_url}. "
            "Run `unpack install --server ... --token ...` or set UNPACK_TOKEN."
        )

    endpoint = f"{server_url.rstrip('/')}/ingest"
    raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(raw_bytes)

    headers = {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Accept": "application/json",
        "User-Agent": f"unpack-cli/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(endpoint, data=compressed, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            if not body:
                return {"status_code": resp.status}
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
                return {"status_code": resp.status, "body": parsed}
            except json.JSONDecodeError:
                return {"status_code": resp.status, "raw": body}
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            pass
        detail = f": {err_body[:200]}" if err_body else ""
        raise IngestError(f"server returned HTTP {exc.code} for {endpoint}{detail}") from exc
    except urllib.error.URLError as exc:
        raise IngestError(f"could not reach {endpoint}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise IngestError(f"request to {endpoint} timed out after {timeout_s:.1f}s") from exc


def format_ingest_result(
    response: dict[str, Any],
    *,
    branch: str,
    head_sha: str,
    redactions: dict[str, int],
    has_session: bool,
) -> str:
    """Format a single concise status line for CLI / hook output."""
    short_sha = head_sha[:7]
    analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
    public_id = analysis.get("public_id")
    url = analysis.get("url")
    dedup = bool(response.get("deduplicated"))
    status = "reused existing analysis" if dedup else "analysis queued"

    parts = [f"Unpack: {status} for {branch} ({short_sha})"]
    if public_id:
        parts.append(f"[{public_id}]")
    if not has_session:
        parts.append("(no session found)")
    redacted_total = sum(redactions.values())
    if redacted_total:
        parts.append(f"(redacted {redacted_total} secret{'s' if redacted_total != 1 else ''})")
    if url:
        parts.append(f"-> {url}")
    return " ".join(parts)
