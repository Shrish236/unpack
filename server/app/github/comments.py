"""PR comment: body builder and create-or-update (server design §8.3, §8.4)."""

from __future__ import annotations

from typing import Any

from ..config import settings
from .service import GitHubService

MARKER_PREFIX = "<!-- unpack:v1 "


def _code(text: Any) -> str:
    """Function names and other user-derived text go in code spans, where Markdown does not apply."""
    s = str(text).replace("`", "'").replace("\r", " ").replace("\n", " ")
    return f"`{s}`"


def build_comment_body(
    *,
    analysis_public_id: str,
    short_sha: str,
    summary: str,
    stats: dict[str, Any],
    not_reached: list[str],
    banner_message: str | None,
    image_url: str | None,
    live_url: str,
    generated_at: str,
    max_flags: int = 5,
    max_chars: int = 60000,
) -> str:
    lines: list[str] = [f"{MARKER_PREFIX}analysis={analysis_public_id} -->", "### 🧭 Unpack: what this change did and why", ""]
    if banner_message:
        lines += [f"> ⚠️ {banner_message}", ""]
    if summary:
        lines += [f"**Summary.** {summary}", ""]

    by_change = stats.get("by_change", {})
    functions = stats.get("functions_changed", 0)
    rows = [
        "| | |",
        "|---|---|",
        f"| Functions changed | **{functions}** ({by_change.get('added', 0)} added, "
        f"{by_change.get('functional', 0)} modified, {by_change.get('signature', 0)} signature, "
        f"{by_change.get('text_only', 0)} formatting only, {by_change.get('deleted', 0)} deleted) |",
    ]
    flags: list[str] = []
    for name in not_reached:
        flags.append(f"⚠️ Not reached by any test: {_code(name)}")
    shown = flags[:max_flags]
    for flag in shown:
        rows.append(f"| {flag} | |")
    if len(flags) > max_flags:
        rows.append(f"| and {len(flags) - max_flags} more in the live graph | |")
    if functions == 0:
        rows.append("| No code functions changed | |")
    lines += rows + [""]

    if image_url:
        lines += [f"[![Graph of the changed code]({image_url})]({live_url})", ""]
    # With PUBLIC_VIEWER the live graph opens without a login, so the comment does not ask for one.
    access = "" if settings.PUBLIC_VIEWER else " (GitHub login and repo access required)"
    lines += [
        f"**[Open the live graph →]({live_url})** · reasons and evidence for each function{access}",
        "",
        f"<sub>Analysis of `{short_sha}` · updated {generated_at}</sub>",
    ]
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[: max_chars - 40] + "\n\n_Truncated; see the live graph._"
    return body


async def list_comments(svc: GitHubService, token: str, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
    return await svc.paginate(f"/repos/{owner}/{repo}/issues/{number}/comments", token)


async def find_unpack_comment(
    svc: GitHubService, token: str, owner: str, repo: str, number: int
) -> dict[str, Any] | None:
    for comment in await list_comments(svc, token, owner, repo, number):
        if MARKER_PREFIX in (comment.get("body") or ""):
            return comment
    return None


async def create_comment(
    svc: GitHubService, token: str, owner: str, repo: str, number: int, body: str
) -> dict[str, Any]:
    data, _ = await svc.request_json(
        "POST", f"/repos/{owner}/{repo}/issues/{number}/comments", token=token, json={"body": body}
    )
    return data


async def update_comment(
    svc: GitHubService, token: str, owner: str, repo: str, comment_id: int, body: str
) -> dict[str, Any] | None:
    """Returns None when the comment no longer exists (404)."""
    data, response = await svc.request_json(
        "PATCH",
        f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
        token=token,
        json={"body": body},
        allow=(404,),
    )
    return None if response.status_code == 404 else data
