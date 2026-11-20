"""The Unpack section at the top of a pull request description (kept between two markers).

Only the text between the markers is ever rewritten. The author's own description stays as it is.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .service import GitHubService

BEGIN = "<!-- unpack:begin -->"
END = "<!-- unpack:end -->"
MAX_DESCRIPTION_CHARS = 65000  # GitHub's limit is 65,536


def section_for(body: str) -> str:
    return f"{BEGIN}\n{body}\n{END}"


def merge(existing: str, section: str) -> str:
    """Replaces the section between the markers, or puts it at the top if there is none."""
    if BEGIN in existing and END in existing:
        before = existing[: existing.index(BEGIN)]
        after = existing[existing.index(END) + len(END):]
        return f"{before}{section}{after}"
    if not existing.strip():
        return section
    return f"{section}\n\n{existing}"


def digest(section: str) -> str:
    return hashlib.sha256(section.encode("utf-8")).hexdigest()


async def write_section(svc: GitHubService, token: str, owner: str, repo: str, number: int,
                        section: str) -> dict[str, Any]:
    """Returns {"written": bool, "reason": str}. Reads the current description first, so edits made since are kept."""
    data, _ = await svc.request_json("GET", f"/repos/{owner}/{repo}/pulls/{number}", token=token)
    existing = data.get("body") or ""
    merged = merge(existing, section)
    if merged == existing:
        return {"written": False, "reason": "unchanged"}
    if len(merged) > MAX_DESCRIPTION_CHARS:
        return {"written": False, "reason": "description too long"}
    await svc.request_json("PATCH", f"/repos/{owner}/{repo}/pulls/{number}", token=token, json={"body": merged})
    return {"written": True, "reason": "updated"}
