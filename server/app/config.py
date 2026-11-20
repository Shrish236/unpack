"""Server configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base URLs & Server
    UNPACK_BASE_URL: str = "http://localhost:8000"

    # Databases
    DATABASE_URL: str = "postgresql+asyncpg://unpack:unpackpass@localhost:5432/unpack"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "unpackpass"

    # Gemini LLM Settings
    GEMINI_BACKEND: str = "ai_studio"  # "ai_studio" or "vertex"
    GEMINI_API_KEY: str = ""
    GCP_PROJECT: str | None = None
    GCP_LOCATION: str = "us-central1"
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None

    GEMINI_MODEL_PRIMARY: str = "gemini-3.1-pro-preview"
    GEMINI_MODEL_FALLBACK: str = "gemini-2.5-pro"
    GEMINI_MODEL_REPAIR: str = "gemini-3.5-flash"
    GEMINI_TIMEOUT_S: int = 120
    GEMINI_CONCURRENCY: int = 2
    GEMINI_MAX_INPUT_TOKENS: int = 200000
    GEMINI_MAX_OUTPUT_TOKENS: int = 16384
    GEMINI_DAILY_TOKEN_BUDGET_PER_REPO: int = 5000000
    PROMPT_VERSION: int = 1

    # GitHub App
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_APP_ID: str | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str = "/secrets/app.pem"
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    GITHUB_WEBHOOK_SECRET: str | None = None

    # Security
    SESSION_SECRET: str = "default_session_secret_32_characters_min"
    TOKEN_ENCRYPTION_KEY: str = "D7kRj9UqQ3sV4wX8yZ0aBcDeFgHiJkLmNoPqRsTuVwX="
    RENDER_TOKEN_SECRET: str = "default_render_token_secret_min32chars"
    ADMIN_TOKEN: str = "unp_admin_secret_token_default"

    # Storage & Reconciler
    DATA_DIR: str = "/data"
    WORKER_CONCURRENCY: int = 2
    RECONCILE_INTERVAL_SECONDS: int = 30
    TRACK_MAX_DAYS: int = 7
    MAX_GRAPH_NODES: int = 200
    MAX_GRAPH_EDGES: int = 500
    MAX_NEIGHBORS_PER_NODE: int = 15
    IMPACT_DEPTH: int = 3
    MAX_LLM_FUNCTIONS: int = 50


settings = Settings()
