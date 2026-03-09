"""
ACLED API OAuth authentication (acleddata.com).
Uses ACLED_EMAIL + ACLED_PASSWORD to obtain a Bearer token (valid 24h).
See: https://acleddata.com/api-documentation/getting-started
"""
import os
import time
from typing import Optional

import httpx

TOKEN_URL = "https://acleddata.com/oauth/token"
# In-memory cache: (token, expires_at_ts). Refresh when < 1 hour left.
_cached_token: Optional[str] = None
_cached_expires: float = 0
_REFRESH_BEFORE_EXPIRY_SEC = 3600  # 1 hour


def get_acled_token_sync() -> Optional[str]:
    """Synchronous: get ACLED OAuth token (cached). Uses ACLED_EMAIL and ACLED_PASSWORD."""
    global _cached_token, _cached_expires
    now = time.time()
    if _cached_token and _cached_expires > now + _REFRESH_BEFORE_EXPIRY_SEC:
        return _cached_token
    email = (os.getenv("ACLED_EMAIL") or "").strip()
    password = (os.getenv("ACLED_PASSWORD") or "").strip()
    if not email or not password:
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                TOKEN_URL,
                data={
                    "username": email,
                    "password": password,
                    "grant_type": "password",
                    "client_id": "acled",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))  # 24h default
        if token:
            _cached_token = token
            _cached_expires = now + expires_in
            return token
    except Exception:
        _cached_token = None
        _cached_expires = 0
    return None


async def get_acled_token_async() -> Optional[str]:
    """Async: get ACLED OAuth token (cached). Uses ACLED_EMAIL and ACLED_PASSWORD."""
    global _cached_token, _cached_expires
    now = time.time()
    if _cached_token and _cached_expires > now + _REFRESH_BEFORE_EXPIRY_SEC:
        return _cached_token
    email = (os.getenv("ACLED_EMAIL") or "").strip()
    password = (os.getenv("ACLED_PASSWORD") or "").strip()
    if not email or not password:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "username": email,
                    "password": password,
                    "grant_type": "password",
                    "client_id": "acled",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))
        if token:
            _cached_token = token
            _cached_expires = now + expires_in
            return token
    except Exception:
        _cached_token = None
        _cached_expires = 0
    return None


def has_acled_oauth() -> bool:
    """True if ACLED_EMAIL and ACLED_PASSWORD are set (OAuth flow)."""
    return bool((os.getenv("ACLED_EMAIL") or "").strip() and (os.getenv("ACLED_PASSWORD") or "").strip())
