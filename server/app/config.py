"""Server configuration loaded from environment variables.

Secrets have no committed defaults. `required_problems()` lists anything missing
or too weak, and the API and worker refuse to start when that list is not empty.
"""

from __future__ import annotations

import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Public URL (tunnel) and the internal URL the worker uses to reach /render
    UNPACK_BASE_URL: str = ""
    INTERNAL_API_URL: str = "http://127.0.0.1:8000"

    # Databases
    DATABASE_URL: str = ""

    # Reasoning (LLM) is a placeholder in this build. Gemini settings are kept for later.
    REASONING_ENABLED: bool = False
    DASHBOARD_TEAM_ID: str = "payments"  # measured sessions are shown under this team until a team mapping exists
    CANDIDATE_MIN_SESSIONS: int = 2  # a repeated override becomes a policy candidate at this many sessions
    GEMINI_BACKEND: str = "ai_studio"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_PRIMARY: str = "gemini-3.5-flash"
    GEMINI_MODEL_FALLBACK: str = "gemini-3.7-flash"
    GEMINI_MODEL_REPAIR: str = "gemini-3.5-flash"
    GEMINI_TIMEOUT_S: int = 120
    GEMINI_CONCURRENCY: int = 2
    GEMINI_MAX_INPUT_TOKENS: int = 200000
    GEMINI_MAX_OUTPUT_TOKENS: int = 16384
    GEMINI_DAILY_TOKEN_BUDGET_PER_REPO: int = 5000000
    PROMPT_VERSION: int = 2
    GRAPH_CONTEXT_ENABLED: bool = True  # put callers, callees and test reach of changed functions in the prompts
    LLM_GRAPH_TOOLS: bool = False  # let the model look things up in the code graph before it answers (extra calls)
    GRAPH_TOOLS_MAX_CALLS: int = 24

    # GitHub App and OAuth
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_OAUTH_URL: str = "https://github.com/login/oauth"
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_SLUG: str = "unpack"
    GITHUB_APP_PRIVATE_KEY_PATH: str = "/secrets/app.pem"
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None

    # Secrets (required, no defaults)
    SESSION_SECRET: str = ""
    TOKEN_ENCRYPTION_KEY: str = ""
    RENDER_TOKEN_SECRET: str = ""
    ADMIN_TOKEN: str = ""

    # Optional path to a Chromium binary for rendering (the Docker image installs one;
    # set this only when the Playwright-managed browser is not available)
    RENDER_CHROMIUM_PATH: str | None = None

    # Storage and limits
    DATA_DIR: str = "/data"
    WORKER_CONCURRENCY: int = 2
    # Poller: one sweep per interval over branches with pending posts (no webhooks)
    RECONCILE_INTERVAL_SECONDS: int = 10
    # A pushed branch with no pull request is held this many days, then abandoned (posting is on demand later)
    PR_WAIT_DAYS: int = 3
    # Also write the Unpack section at the top of the pull request description
    PR_DESCRIPTION_SECTION: bool = True
    INSTALLATION_SYNC_SECONDS: int = 900
    MAX_GRAPH_NODES: int = 200
    MAX_GRAPH_EDGES: int = 500
    MAX_NEIGHBORS_PER_NODE: int = 15
    IMPACT_DEPTH: int = 3
    MAX_LLM_FUNCTIONS: int = 50
    MAX_PAYLOAD_COMPRESSED_BYTES: int = 25 * 1024 * 1024
    MAX_PAYLOAD_UNCOMPRESSED_BYTES: int = 150 * 1024 * 1024
    PUSHES_PER_MINUTE_PER_REPO: int = 60
    ACCESS_CACHE_SECONDS: int = 600
    JOB_STUCK_SECONDS: int = 600
    # Analyses run in this many worker processes (graph building is CPU-bound Python). 0 = in-process threads.
    ANALYSIS_PROCESSES: int = 0
    # Graphs kept loaded in memory per process for the read endpoints.
    GRAPH_LRU_SIZE: int = 1
    # Concurrent branch checks in the reconciler.
    RECONCILE_CONCURRENCY: int = 8
    # Local development only: when set, the viewer endpoints accept requests with no login and act as this
    # user, with access to every repository. Refused unless UNPACK_BASE_URL points at localhost.
    DEV_VIEWER_LOGIN: str = ""

    def required_problems(self) -> list[str]:
        """Return a human-readable line for each missing or weak required setting."""
        problems: list[str] = []
        if not self.UNPACK_BASE_URL:
            problems.append("UNPACK_BASE_URL is not set")
        if not self.DATABASE_URL:
            problems.append("DATABASE_URL is not set")
        for name in ("SESSION_SECRET", "RENDER_TOKEN_SECRET", "ADMIN_TOKEN"):
            value = getattr(self, name)
            if not value:
                problems.append(f"{name} is not set")
            elif len(value) < 32:
                problems.append(f"{name} must be at least 32 characters")
        if self.DEV_VIEWER_LOGIN and not re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", self.UNPACK_BASE_URL):
            problems.append("DEV_VIEWER_LOGIN is only allowed when UNPACK_BASE_URL is localhost or 127.0.0.1")
        if not self.TOKEN_ENCRYPTION_KEY:
            problems.append("TOKEN_ENCRYPTION_KEY is not set")
        else:
            try:
                from cryptography.fernet import Fernet

                Fernet(self.TOKEN_ENCRYPTION_KEY.encode())
            except Exception:
                problems.append("TOKEN_ENCRYPTION_KEY is not a valid Fernet key")
        return problems


settings = Settings()


def require_valid_settings() -> None:
    """Exit with a clear message if required settings are missing. Called at startup."""
    problems = settings.required_problems()
    if problems:
        raise SystemExit("Unpack refuses to start:\n  - " + "\n  - ".join(problems))
