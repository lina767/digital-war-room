"""
Sentinel Hub OAuth authentication helper with in-memory token cache.
Uses SENTINELHUB_CLIENT_ID + SENTINELHUB_CLIENT_SECRET.
"""

import logging
import os
import time
from typing import Optional

import httpx

from .http_client import get_http_client

logger = logging.getLogger(__name__)

TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"

_cached_token: Optional[str] = None
_cached_expires_at: float = 0.0
_REFRESH_BEFORE_EXPIRY_SEC = 300  # refresh 5 minutes early


def has_sentinelhub_credentials() -> bool:
    return bool((os.getenv("SENTINELHUB_CLIENT_ID") or "").strip() and (os.getenv("SENTINELHUB_CLIENT_SECRET") or "").strip())


async def get_sentinelhub_token_async() -> Optional[str]:
    global _cached_token, _cached_expires_at

    now = time.time()
    if _cached_token and _cached_expires_at > now + _REFRESH_BEFORE_EXPIRY_SEC:
        return _cached_token

    client_id = (os.getenv("SENTINELHUB_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("SENTINELHUB_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        logger.info(
            "Sentinel Hub OAuth: no credentials. Set SENTINELHUB_CLIENT_ID and SENTINELHUB_CLIENT_SECRET in backend/.env."
        )
        return None

    try:
        http_client = get_http_client()
        resp = await http_client.request(
            "POST",
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            retries=1,
        )
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        if token:
            _cached_token = token
            _cached_expires_at = now + expires_in
            return token
    except httpx.HTTPStatusError as e:
        body_preview = ""
        try:
            body_preview = e.response.text[:200]
        except Exception:
            pass
        logger.warning("Sentinel Hub OAuth token failed: HTTP %s – %s", e.response.status_code, body_preview)
    except Exception as e:
        logger.warning("Sentinel Hub OAuth token request failed: %s", e)

    _cached_token = None
    _cached_expires_at = 0.0
    return None
