"""Pull request and installation calls (server design §3.2, §3.3, §8.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .service import GitHubError, GitHubService


@dataclass
class CompareResult:
    status: str  # ahead | behind | identical | diverged
    ahead_by: int
    behind_by: int


async def list_open_prs_for_head(
    svc: GitHubService, token: str, owner: str, repo: str, branch: str
) -> list[dict[str, Any]]:
    return await svc.paginate(
        f"/repos/{owner}/{repo}/pulls", token, {"head": f"{owner}:{branch}", "state": "open"}
    )


async def get_pr(svc: GitHubService, token: str, owner: str, repo: str, number: int) -> dict[str, Any]:
    data, _ = await svc.request_json("GET", f"/repos/{owner}/{repo}/pulls/{number}", token=token)
    return data


async def compare(
    svc: GitHubService, token: str, owner: str, repo: str, base: str, head: str
) -> CompareResult:
    data, _ = await svc.request_json("GET", f"/repos/{owner}/{repo}/compare/{base}...{head}", token=token)
    return CompareResult(status=data["status"], ahead_by=data.get("ahead_by", 0), behind_by=data.get("behind_by", 0))


async def installation_id_for_repo(svc: GitHubService, owner: str, repo: str) -> int | None:
    """Uses the App JWT. None means the App is not installed on this repository."""
    data, response = await svc.request_json(
        "GET", f"/repos/{owner}/{repo}/installation", token=svc.app_jwt(), allow=(404,)
    )
    if response.status_code == 404:
        return None
    return int(data["id"])


async def installation_repositories(svc: GitHubService, installation_id: int) -> list[dict[str, Any]]:
    token = await svc.installation_token(installation_id)
    return await svc.paginate("/installation/repositories", token)


async def get_viewer_repo(svc: GitHubService, user_token: str, owner: str, repo: str) -> int:
    """Returns the HTTP status for the viewer's access check (200 allowed, 404/403 denied, 401 revoked)."""
    _, response = await svc.request_json(
        "GET", f"/repos/{owner}/{repo}", token=user_token, allow=(401, 403, 404)
    )
    return response.status_code


async def get_viewer_user(svc: GitHubService, user_token: str) -> dict[str, Any]:
    data, _ = await svc.request_json("GET", "/user", token=user_token)
    return data


__all__ = [
    "CompareResult",
    "GitHubError",
    "compare",
    "get_pr",
    "get_viewer_repo",
    "get_viewer_user",
    "installation_id_for_repo",
    "installation_repositories",
    "list_open_prs_for_head",
]
