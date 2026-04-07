"""
ACLED API OAuth authentication (acleddata.com).
Uses ACLED_EMAIL + ACLED_PASSWORD to obtain a Bearer token (valid 24h).
See: https://acleddata.com/api-documentation/getting-started
"""

import logging
import os
import time
import asyncio
from typing import Optional

import httpx
from services.http_client import CircuitOpenError, get_http_client

logger = logging.getLogger(__name__)

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
        logger.info(
            "ACLED OAuth: no credentials. Set ACLED_EMAIL and ACLED_PASSWORD in backend/.env (myACLED account at acleddata.com)."
        )
        return None
    try:
        data = asyncio.run(_fetch_acled_token_data_async(email=email, password=password))
        if not data:
            _cached_token = None
            _cached_expires = 0
            return None
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))  # 24h default
        if token:
            _cached_token = token
            _cached_expires = now + expires_in
            return token
    except RuntimeError:
        # Fallback path if sync call happens inside a running event loop.
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
                if resp.status_code != 200:
                    try:
                        err_body = resp.json()
                        err_msg = err_body.get("error_description") or err_body.get("error") or resp.text[:200]
                    except Exception:
                        err_msg = resp.text[:200] if resp.text else str(resp.status_code)
                    logger.warning(
                        "ACLED OAuth token failed: HTTP %s – %s. Check ACLED_EMAIL/ACLED_PASSWORD (myACLED login).",
                        resp.status_code,
                        err_msg,
                    )
                    _cached_token = None
                    _cached_expires = 0
                    return None
                data = resp.json()
            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 86400))
            if token:
                _cached_token = token
                _cached_expires = now + expires_in
                return token
        except Exception as e:
            logger.warning("ACLED OAuth token request failed: %s. Check credentials and network.", e)
            _cached_token = None
            _cached_expires = 0
            return None
    except Exception as e:
        logger.warning("ACLED OAuth token request failed: %s. Check credentials and network.", e)
        _cached_token = None
        _cached_expires = 0
    return None


async def _fetch_acled_token_data_async(*, email: str, password: str) -> Optional[dict]:
    client = get_http_client()
    try:
        resp = await client.request(
            "POST",
            TOKEN_URL,
            data={
                "username": email,
                "password": password,
                "grant_type": "password",
                "client_id": "acled",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
            retries=2,
            service_name="acled_oauth",
        )
        return resp.json()
    except CircuitOpenError:
        logger.warning("ACLED OAuth token skipped: circuit breaker open")
        return None
    except httpx.HTTPStatusError as e:
        try:
            err_body = e.response.json()
            err_msg = err_body.get("error_description") or err_body.get("error") or e.response.text[:200]
        except Exception:
            err_msg = e.response.text[:200] if e.response.text else str(e.response.status_code)
        logger.warning(
            "ACLED OAuth token failed: HTTP %s – %s. Check ACLED_EMAIL/ACLED_PASSWORD (myACLED login).",
            e.response.status_code,
            err_msg,
        )
        return None
    except Exception as e:
        logger.warning("ACLED OAuth token request failed: %s. Check credentials and network.", e)
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
        logger.info(
            "ACLED OAuth: no credentials. Set ACLED_EMAIL and ACLED_PASSWORD in backend/.env (myACLED account at acleddata.com)."
        )
        return None
    try:
        data = await _fetch_acled_token_data_async(email=email, password=password)
        if not data:
            _cached_token = None
            _cached_expires = 0
            return None
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))
        if token:
            _cached_token = token
            _cached_expires = now + expires_in
            return token
    except Exception as e:
        logger.warning("ACLED OAuth token request failed: %s. Check credentials and network.", e)
        _cached_token = None
        _cached_expires = 0
    return None


def has_acled_oauth() -> bool:
    """True if ACLED_EMAIL and ACLED_PASSWORD are set (OAuth flow)."""
    return bool((os.getenv("ACLED_EMAIL") or "").strip() and (os.getenv("ACLED_PASSWORD") or "").strip())
