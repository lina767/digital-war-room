"""Async request context: tenant, user, role (ContextVar for non-HTTP code paths)."""

from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

AuthMethod = Literal["jwt", "api_key", "default"]


@dataclass(frozen=True)
class RequestContext:
    tenant_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    role: str
    auth_method: AuthMethod


_ctx: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar("dwr_request_context", default=None)


def set_request_context(ctx: RequestContext) -> contextvars.Token[Optional[RequestContext]]:
    return _ctx.set(ctx)


def reset_request_context(token: contextvars.Token[Optional[RequestContext]]) -> None:
    _ctx.reset(token)


def get_request_context() -> Optional[RequestContext]:
    return _ctx.get()


def get_current_tenant_id() -> uuid.UUID:
    c = _ctx.get()
    if c is not None:
        return c.tenant_id
    from services.tenant_constants import get_default_tenant_id

    return get_default_tenant_id()


def get_current_user_id() -> Optional[uuid.UUID]:
    c = _ctx.get()
    return c.user_id if c else None
