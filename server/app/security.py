"""Tokens, signatures and encryption helpers (server design §11)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from cryptography.fernet import Fernet

from .config import settings

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _base62(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = []
    while n:
        n, r = divmod(n, 62)
        out.append(BASE62[r])
    return "".join(reversed(out)) or "0"


def new_ingest_token() -> str:
    """unp_ + 32 random bytes in base62, as the design specifies."""
    body = _base62(secrets.token_bytes(32))
    return "unp_" + body.rjust(43, "0")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_public_id() -> str:
    """22-character URL-safe identifier."""
    return secrets.token_urlsafe(16)[:22]


def new_file_name() -> str:
    """32 random hex characters for rendered images (camo caches by URL)."""
    return secrets.token_hex(16)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _hmac(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def render_token(public_id: str, ttl_seconds: int = 60, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + ttl_seconds)
    return f"{expires}.{_hmac(settings.RENDER_TOKEN_SECRET, f'{public_id}:{expires}')}"


def verify_render_token(public_id: str, token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    expires_text, signature = token.split(".", 1)
    try:
        expires = int(expires_text)
    except ValueError:
        return False
    current = now if now is not None else time.time()
    if current > expires:
        return False
    expected = _hmac(settings.RENDER_TOKEN_SECRET, f"{public_id}:{expires}")
    return hmac.compare_digest(expected, signature)


def _fernet() -> Fernet:
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
