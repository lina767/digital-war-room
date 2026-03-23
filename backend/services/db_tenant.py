"""Set Postgres session variables for RLS (app.active_tenant_id, app.current_user_id)."""

from __future__ import annotations

import uuid
from typing import Optional

import asyncpg


async def set_session_tenant(
    conn: asyncpg.Connection,
    tenant_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
) -> None:
    await conn.execute("SELECT set_config('app.active_tenant_id', $1, true)", str(tenant_id))
    if user_id is not None:
        await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
    else:
        await conn.execute("SELECT set_config('app.current_user_id', '', true)")
