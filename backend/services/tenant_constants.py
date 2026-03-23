"""Default tenant UUID for legacy and background jobs (matches migration 003 seed)."""

from __future__ import annotations

import os
import uuid

_BUILTIN_DEFAULT = uuid.UUID("00000000-0000-4000-8000-000000000001")


def get_default_tenant_id() -> uuid.UUID:
    raw = (os.getenv("DEFAULT_TENANT_ID") or "").strip()
    if raw:
        return uuid.UUID(raw)
    return _BUILTIN_DEFAULT
