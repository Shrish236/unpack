"""Per-repository configuration storage for the Unpack CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class RepoConfig:
    """Resolved Unpack configuration for a single repository."""

    server_url: str = DEFAULT_SERVER_URL
    token: str | None = None
    default_branch: str | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S


def get_config_path() -> Path:
    """Return path to the user-level Unpack config JSON file."""
    override = os.environ.get("UNPACK_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "unpack" / "config.json"


def normalize_repo_key(repo_root: Path) -> str:
    """Return canonical realpath string used as key in config.json."""
    return os.path.realpath(str(repo_root))


def load_config_data(config_path: Path | None = None) -> dict[str, Any]:
    """Load raw JSON config data, returning an empty structure if missing or invalid."""
    path = config_path or get_config_path()
    if not path.exists():
        return {"repos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("repos"), dict):
            return data
    except Exception:
        pass
    return {"repos": {}}


def save_config_data(data: dict[str, Any], config_path: Path | None = None) -> Path:
    """Persist config JSON with owner-only permissions."""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def save_repo_config(
    repo_root: Path,
    *,
    server_url: str,
    token: str | None = None,
    default_branch: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    config_path: Path | None = None,
) -> Path:
    """Save or update configuration for a repository."""
    data = load_config_data(config_path)
    key = normalize_repo_key(repo_root)
    entry: dict[str, Any] = {
        "server_url": server_url.rstrip("/"),
        "timeout_s": float(timeout_s),
    }
    if token:
        entry["token"] = token
    if default_branch:
        entry["default_branch"] = default_branch

    data.setdefault("repos", {})[key] = entry
    return save_config_data(data, config_path)


def remove_repo_config(repo_root: Path, config_path: Path | None = None) -> bool:
    """Remove a repository entry from config.json if present."""
    data = load_config_data(config_path)
    repos = data.get("repos", {})
    key = normalize_repo_key(repo_root)
    if key not in repos:
        return False
    del repos[key]
    save_config_data(data, config_path)
    return True


def get_stored_repo_config(
    repo_root: Path, config_path: Path | None = None
) -> dict[str, Any] | None:
    """Return raw stored config dict for repo_root, or None if not configured."""
    data = load_config_data(config_path)
    repos = data.get("repos", {})
    key = normalize_repo_key(repo_root)
    entry = repos.get(key)
    if isinstance(entry, dict):
        return entry
    # Fallback to non-resolved path string if saved that way
    raw_entry = repos.get(str(repo_root))
    return raw_entry if isinstance(raw_entry, dict) else None


def resolve_repo_config(
    repo_root: Path,
    *,
    server_override: str | None = None,
    token_override: str | None = None,
    default_branch_override: str | None = None,
    timeout_override: float | None = None,
    config_path: Path | None = None,
) -> RepoConfig:
    """Resolve effective config: CLI overrides > env vars > stored config > defaults."""
    stored = get_stored_repo_config(repo_root, config_path) or {}

    server_url = (
        server_override
        or os.environ.get("UNPACK_SERVER")
        or stored.get("server_url")
        or DEFAULT_SERVER_URL
    ).rstrip("/")

    token = token_override or os.environ.get("UNPACK_TOKEN") or stored.get("token") or None

    default_branch = (
        default_branch_override
        or os.environ.get("UNPACK_DEFAULT_BRANCH")
        or stored.get("default_branch")
        or None
    )

    timeout_raw: Any = (
        timeout_override
        if timeout_override is not None
        else os.environ.get("UNPACK_TIMEOUT") or stored.get("timeout_s") or DEFAULT_TIMEOUT_S
    )
    try:
        timeout_s = float(timeout_raw)
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT_S

    return RepoConfig(
        server_url=server_url,
        token=token,
        default_branch=default_branch,
        timeout_s=timeout_s,
    )
