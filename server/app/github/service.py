"""GitHub REST access: App JWT, installation tokens, viewer tokens (server design §8.2).

Every call goes through `_send`, which applies one retry for 5xx responses and maps
rate limits to `RateLimited` so the job runner can delay the work until the reset.
"""

from __future__ import annotations

import asyncio
import calendar
import time
from typing import Any

import httpx
import jwt

API_VERSION = "2022-11-28"


class GitHubError(Exception):
    def __init__(self, status: int, message: str, body: Any = None) -> None:
        super().__init__(f"GitHub {status}: {message}")
        self.status = status
        self.body = body


class RateLimited(GitHubError):
    def __init__(self, retry_after: float, message: str = "rate limited") -> None:
        super().__init__(429, message)
        self.retry_after = retry_after


class GitHubService:
    def __init__(
        self,
        api_url: str,
        app_id: str | None = None,
        private_key_pem: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.app_id = app_id
        self.private_key_pem = private_key_pem
        self.http = httpx.AsyncClient(base_url=self.api_url, timeout=30.0, transport=transport)
        self._installation_tokens: dict[int, tuple[str, float]] = {}

    async def aclose(self) -> None:
        await self.http.aclose()

    # ---- auth -------------------------------------------------------------

    def app_jwt(self) -> str:
        if not self.app_id or not self.private_key_pem:
            raise GitHubError(0, "GitHub App is not configured (GITHUB_APP_ID / private key)")
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.app_id},
            self.private_key_pem,
            algorithm="RS256",
        )

    async def installation_token(self, installation_id: int) -> str:
        cached = self._installation_tokens.get(installation_id)
        if cached and cached[1] - time.time() > 300:
            return cached[0]
        data, _ = await self.request_json(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self.app_jwt(),
        )
        token = data["token"]
        expires = calendar.timegm(time.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ"))  # UTC, not local time
        self._installation_tokens[installation_id] = (token, expires)
        return token

    # ---- transport ----------------------------------------------------------

    async def _send(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        all_headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
        if token:
            all_headers["Authorization"] = f"Bearer {token}"
        if headers:
            all_headers.update(headers)

        attempts = 0
        while True:
            attempts += 1
            response = await self.http.request(method, path, json=json, params=params, headers=all_headers)
            if response.status_code in (403, 429) and (
                response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after")
            ):
                retry_after = float(response.headers.get("retry-after", "60"))
                raise RateLimited(retry_after, "GitHub rate limit")
            if response.status_code >= 500 and attempts < 3:
                await asyncio.sleep(0.5 * attempts)
                continue
            return response

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow: tuple[int, ...] = (),
    ) -> tuple[Any, httpx.Response]:
        response = await self._send(method, path, token=token, json=json, params=params, headers=headers)
        if response.status_code >= 400 and response.status_code not in allow:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise GitHubError(response.status_code, f"{method} {path}", body)
        data = response.json() if response.content else None
        return data, response

    async def paginate(self, path: str, token: str, params: dict[str, Any] | None = None) -> list[Any]:
        items: list[Any] = []
        url: str | None = path
        query = dict(params or {})
        query.setdefault("per_page", 100)
        while url:
            response = await self._send("GET", url, token=token, params=query)
            if response.status_code >= 400:
                raise GitHubError(response.status_code, f"GET {url}", response.text)
            data = response.json()
            items.extend(data if isinstance(data, list) else data.get("repositories", []))
            url = None
            query = {}
            link = response.headers.get("link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part[part.index("<") + 1 : part.index(">")]
                    url = url.replace(self.api_url, "")
        return items
