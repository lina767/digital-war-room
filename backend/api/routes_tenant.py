"""
Multi-tenancy: current user context and tenant API keys (RBAC: owner/admin create/revoke).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Any, List, Optional

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from middleware.tenant_context import get_request_ctx

router = APIRouter()


@router.get("/auth/me")
async def auth_me(request: Request) -> Any:
    """Return resolved tenant and role for the current JWT or API key."""
    ctx = get_request_ctx(request)
    return {
        "tenant_id": str(ctx.tenant_id),
        "user_id": str(ctx.user_id) if ctx.user_id else None,
        "role": ctx.role,
        "auth_method": ctx.auth_method,
    }


class CreateApiKeyBody(BaseModel):
    name: str = Field(default="", max_length=120)


def _db() -> Optional[str]:
    import os

    return (os.getenv("DATABASE_URL") or "").strip() or None


@router.post("/tenant/api-keys")
async def create_tenant_api_key(request: Request, body: CreateApiKeyBody) -> Any:
    ctx = get_request_ctx(request)
    if ctx.auth_method == "api_key":
        return JSONResponse(status_code=403, content={"error": "Cannot create API keys using an API key"})
    if ctx.role not in ("owner", "admin"):
        return JSONResponse(status_code=403, content={"error": "owner or admin role required"})
    if ctx.user_id is None:
        return JSONResponse(status_code=400, content={"error": "JWT with user id required"})

    raw = f"dwr_{secrets.token_hex(16)}_{secrets.token_hex(16)}"
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = raw[:12]

    url = _db()
    if not url:
        return JSONResponse(status_code=503, content={"error": "DATABASE_URL not configured"})

    conn = await asyncpg.connect(url, timeout=10.0)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO tenant_api_keys (tenant_id, name, key_prefix, key_hash, scopes)
            VALUES ($1, $2, $3, $4, '[]'::jsonb)
            RETURNING id, created_at
            """,
            ctx.tenant_id,
            body.name.strip() or "API key",
            prefix,
            key_hash,
        )
    finally:
        await conn.close()

    return {
        "id": str(row["id"]),
        "name": body.name.strip() or "API key",
        "key_prefix": prefix,
        "api_key": raw,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "warning": "Store this key securely; it will not be shown again.",
    }


@router.get("/tenant/api-keys")
async def list_tenant_api_keys(request: Request) -> Any:
    ctx = get_request_ctx(request)
    if ctx.role not in ("owner", "admin"):
        return JSONResponse(status_code=403, content={"error": "owner or admin role required"})
    url = _db()
    if not url:
        return JSONResponse(status_code=503, content={"error": "DATABASE_URL not configured"})
    conn = await asyncpg.connect(url, timeout=10.0)
    try:
        rows = await conn.fetch(
            """
            SELECT id, name, key_prefix, created_at, revoked_at
            FROM tenant_api_keys
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            """,
            ctx.tenant_id,
        )
    finally:
        await conn.close()
    out: List[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r["id"]),
                "name": r["name"],
                "key_prefix": r["key_prefix"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "revoked": r["revoked_at"] is not None,
            }
        )
    return {"keys": out}


@router.delete("/tenant/api-keys/{key_id}")
async def revoke_tenant_api_key(request: Request, key_id: str) -> Any:
    ctx = get_request_ctx(request)
    if ctx.role not in ("owner", "admin"):
        return JSONResponse(status_code=403, content={"error": "owner or admin role required"})
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid key id"})
    url = _db()
    if not url:
        return JSONResponse(status_code=503, content={"error": "DATABASE_URL not configured"})
    conn = await asyncpg.connect(url, timeout=10.0)
    try:
        res = await conn.execute(
            """
            UPDATE tenant_api_keys SET revoked_at = NOW()
            WHERE id = $1 AND tenant_id = $2 AND revoked_at IS NULL
            """,
            kid,
            ctx.tenant_id,
        )
    finally:
        await conn.close()
    if res == "UPDATE 0":
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"status": "revoked", "id": key_id}


class MembershipBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(default="member")


@router.post("/tenant/memberships")
async def add_tenant_membership(request: Request, body: MembershipBody) -> Any:
    """
    Bootstrap: add a user to the active tenant (owner only). Used to link Supabase auth.users to a tenant.
    """
    ctx = get_request_ctx(request)
    if ctx.role != "owner":
        return JSONResponse(status_code=403, content={"error": "owner role required"})
    try:
        uid = uuid.UUID(body.user_id.strip())
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid user_id"})
    role = body.role
    if role not in ("owner", "admin", "member", "viewer"):
        return JSONResponse(status_code=400, content={"error": "invalid role"})
    url = _db()
    if not url:
        return JSONResponse(status_code=503, content={"error": "DATABASE_URL not configured"})
    conn = await asyncpg.connect(url, timeout=10.0)
    try:
        await conn.execute(
            """
            INSERT INTO tenant_memberships (tenant_id, user_id, role)
            VALUES ($1, $2, $3)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            ctx.tenant_id,
            uid,
            role,
        )
    finally:
        await conn.close()
    return {"status": "ok", "tenant_id": str(ctx.tenant_id), "user_id": str(uid), "role": role}
