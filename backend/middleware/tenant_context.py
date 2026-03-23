"""
Attach RequestContext to each request and ContextVar for background/agent code paths.
"""

from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.request_context import RequestContext, reset_request_context, set_request_context
from services.tenant_auth import build_request_context

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        auth = request.headers.get("authorization")
        x_key = request.headers.get("x-api-key")
        x_tenant = request.headers.get("x-tenant-id")
        try:
            ctx = await build_request_context(
                authorization=auth,
                x_api_key=x_key,
                x_tenant_id=x_tenant,
            )
        except PermissionError as e:
            return JSONResponse(status_code=401, content={"error": str(e) or "unauthorized"})
        except Exception as e:
            logger.warning("tenant context failed: %s", e)
            return JSONResponse(status_code=500, content={"error": "context_resolution_failed"})

        request.state.request_ctx = ctx
        token = set_request_context(ctx)
        try:
            return await call_next(request)
        finally:
            reset_request_context(token)


def get_request_ctx(request: Request) -> RequestContext:
    return getattr(request.state, "request_ctx", None) or _fallback_ctx()


def _fallback_ctx() -> RequestContext:
    from services.tenant_constants import get_default_tenant_id

    tid = get_default_tenant_id()
    return RequestContext(tenant_id=tid, user_id=None, role="viewer", auth_method="default")
