"""
Resolve tenant + user from X-Api-Key, Authorization Bearer (JWT or API key), and optional X-Tenant-Id.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from typing import Optional, Tuple

import asyncpg
import jwt

from services.request_context import AuthMethod, RequestContext
from services.tenant_constants import get_default_tenant_id

logger = logging.getLogger(__name__)

JWT_ALGORITHMS = ("HS256",)

# API keys: dwr_<32 hex chars>_<32 hex chars> (128 hex total after second underscore)
_API_KEY_RE = re.compile(r"^dwr_[0-9a-f]{32}_[0-9a-f]{32}$", re.IGNORECASE)


def _jwt_secret() -> str:
    return (os.getenv("SUPABASE_JWT_SECRET") or os.getenv("JWT_SECRET") or "").strip()


def _require_auth() -> bool:
    return (os.getenv("MULTI_TENANCY_REQUIRE_AUTH") or "").strip().lower() in ("1", "true", "yes")


def _looks_like_api_key(token: str) -> bool:
    return bool(_API_KEY_RE.match(token.strip()))


def verify_jwt_sub(token: str) -> Optional[uuid.UUID]:
    secret = _jwt_secret()
    if not secret:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=list(JWT_ALGORITHMS),
            audience=os.getenv("JWT_AUDIENCE") or None,
            options={"verify_aud": bool(os.getenv("JWT_AUDIENCE"))},
        )
    except jwt.PyJWTError as e:
        logger.debug("JWT verify failed: %s", e)
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return uuid.UUID(str(sub))
    except (ValueError, TypeError):
        return None


async def _fetch_membership_role(
    conn: asyncpg.Connection, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT role FROM tenant_memberships WHERE tenant_id = $1 AND user_id = $2",
        tenant_id,
        user_id,
    )
    return row["role"] if row else None


async def _fetch_first_tenant_for_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> Optional[Tuple[uuid.UUID, str]]:
    row = await conn.fetchrow(
        "SELECT tenant_id, role FROM tenant_memberships WHERE user_id = $1 ORDER BY created_at ASC LIMIT 1",
        user_id,
    )
    if not row:
        return None
    return row["tenant_id"], row["role"]


async def resolve_api_key_tenant(key: str) -> Optional[Tuple[uuid.UUID, str]]:
    """Return (tenant_id, synthetic role 'api_client') if key valid."""
    key = key.strip()
    if not _looks_like_api_key(key):
        return None
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return None
    try:
        conn = await asyncpg.connect(url, timeout=10.0)
    except Exception as e:
        logger.warning("api key lookup: connect failed: %s", e)
        return None
    try:
        row = await conn.fetchrow(
            "SELECT tenant_id FROM tenant_api_keys WHERE key_hash = $1 AND revoked_at IS NULL",
            h,
        )
        if not row:
            return None
        return row["tenant_id"], "api_client"
    finally:
        await conn.close()


async def build_request_context(
    *,
    authorization: Optional[str],
    x_api_key: Optional[str],
    x_tenant_id: Optional[str],
) -> RequestContext:
    """
    Build RequestContext from headers.
    Priority: X-Api-Key > Bearer API key pattern > Bearer JWT > default tenant.
    """
    default_tid = get_default_tenant_id()

    raw_key = (x_api_key or "").strip()
    bearer: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    if raw_key:
        resolved = await resolve_api_key_tenant(raw_key)
        if resolved:
            tid, role = resolved
            return RequestContext(tenant_id=tid, user_id=None, role=role, auth_method="api_key")
        if _require_auth():
            raise PermissionError("Invalid API key")

    if bearer and _looks_like_api_key(bearer):
        resolved = await resolve_api_key_tenant(bearer)
        if resolved:
            tid, role = resolved
            return RequestContext(tenant_id=tid, user_id=None, role=role, auth_method="api_key")
        if _require_auth():
            raise PermissionError("Invalid API key")

    if bearer and not _looks_like_api_key(bearer):
        user_id = verify_jwt_sub(bearer)
        if user_id is None:
            if _require_auth():
                raise PermissionError("Invalid or missing token")
            return RequestContext(tenant_id=default_tid, user_id=None, role="viewer", auth_method="default")

        url = (os.getenv("DATABASE_URL") or "").strip()
        if not url:
            return RequestContext(tenant_id=default_tid, user_id=user_id, role="member", auth_method="jwt")

        conn = await asyncpg.connect(url, timeout=10.0)
        try:
            explicit_tid: Optional[uuid.UUID] = None
            if x_tenant_id:
                try:
                    explicit_tid = uuid.UUID(x_tenant_id.strip())
                except ValueError:
                    explicit_tid = None

            if explicit_tid is not None:
                role = await _fetch_membership_role(conn, explicit_tid, user_id)
                if role:
                    return RequestContext(tenant_id=explicit_tid, user_id=user_id, role=role, auth_method="jwt")
                if _require_auth():
                    raise PermissionError("Not a member of this tenant")
                return RequestContext(tenant_id=default_tid, user_id=user_id, role="member", auth_method="jwt")

            first = await _fetch_first_tenant_for_user(conn, user_id)
            if first:
                tid, role = first
                return RequestContext(tenant_id=tid, user_id=user_id, role=role, auth_method="jwt")
        finally:
            await conn.close()

        return RequestContext(tenant_id=default_tid, user_id=user_id, role="member", auth_method="jwt")

    if _require_auth():
        raise PermissionError("Authentication required")

    return RequestContext(tenant_id=default_tid, user_id=None, role="viewer", auth_method="default")
