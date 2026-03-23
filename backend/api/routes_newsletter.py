"""
Newsletter routes: subscribe (double opt-in), confirm, unsubscribe, send-daily (cron).
All responses and behaviour follow docs/NEWSLETTER-SPEC.md.
"""

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from agents.pattern_anomalies import attach_pattern_flags
from agents.supervisor import analyze_conflict
from api.http_errors import conflict_bad_request
from middleware.rate_limit import limiter
from middleware.tenant_context import get_request_ctx
from services.newsletter_sender import send_confirmation_email, send_daily_briefing
from services.newsletter_store import (
    add_subscriber,
    apply_resend_contact_sync,
    clear_daily_newsletter_lock_today,
    confirm_subscription,
    get_conflicts_with_subscribers,
    get_subscriber_stats,
    list_confirmed_subscribers,
    mark_daily_newsletter_completed,
    remove_by_unsubscribe_token,
    remove_unconfirmed_subscriber,
    try_acquire_daily_newsletter_lock,
)
from services.request_context import RequestContext, reset_request_context, set_request_context
from services.resend_contacts import (
    fetch_contacts_from_resend,
    mark_contact_unsubscribed,
    resolve_import_segment_id,
    upsert_pending_contact,
    upsert_subscribed_contact,
)
from services.tenant_constants import get_default_tenant_id
from utils.sanitize import sanitize_conflict

from .state_helpers import (
    push_agent_status,
    push_escalation_timeline,
    push_run_history,
)

router = APIRouter()
logger = logging.getLogger(__name__)

ANALYZE_TIMEOUT_SEC = 300
NEWSLETTER_DEFAULT_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"
# Bounded concurrent Resend calls per conflict batch (daily send)
_NEWSLETTER_SEND_PARALLELISM = max(1, min(20, int(os.getenv("NEWSLETTER_SEND_PARALLELISM", "5"))))
_NEWSLETTER_DAILY_DEDUPE = (os.getenv("NEWSLETTER_DAILY_DEDUPE", "true") or "").strip().lower() not in ("0", "false", "no")


class SubscribeBody(BaseModel):
    email: EmailStr = Field(..., description="Subscriber email (double opt-in)")
    # Literal matches utils.sanitize.CONFLICT_MAX_LEN; avoids NameError if imports drift in deploys.
    conflict: str | None = Field(None, max_length=80)

    @field_validator("conflict", mode="before")
    @classmethod
    def _strip_optional_conflict(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("conflict must be a string")
        s = v.strip()
        return s if s else None

    @field_validator("conflict")
    @classmethod
    def _validate_optional_conflict(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return sanitize_conflict(v)


def _conflict_from_resend_contact(contact: dict) -> str:
    raw = (contact.get("first_name") or "").strip() or None
    if raw is None:
        return NEWSLETTER_DEFAULT_CONFLICT
    try:
        return sanitize_conflict(raw)
    except ValueError:
        return NEWSLETTER_DEFAULT_CONFLICT


class SyncFromResendBody(BaseModel):
    segment_id: str | None = Field(
        None,
        max_length=80,
        description="Resend segment UUID; defaults to RESEND_NEWSLETTER_SEGMENT_ID(S) / RESEND_AUDIENCE_ID",
    )


@router.post("/newsletter/subscribe")
@limiter.limit("10/minute")
async def newsletter_subscribe(request: Request, body: SubscribeBody) -> JSONResponse:
    """
    POST /api/newsletter/subscribe – create unconfirmed subscriber and send confirmation email.
    """
    email = (body.email or "").strip().lower()
    if body.conflict is not None:
        conflict = body.conflict
    else:
        try:
            conflict = sanitize_conflict(NEWSLETTER_DEFAULT_CONFLICT)
        except ValueError as e:
            return conflict_bad_request(e)
    tid = str(get_request_ctx(request).tenant_id)
    confirm_token, unsubscribe_token = add_subscriber(email, conflict, tenant_id=tid)
    if confirm_token is None:
        return JSONResponse(
            status_code=409,
            content={"error": "This email is already subscribed or pending confirmation."},
        )
    pending_synced = await upsert_pending_contact(email, conflict)
    if not pending_synced:
        # Best-effort: don't block confirmation email flow if Resend Contacts sync fails.
        pass
    sent = await send_confirmation_email(email, conflict, confirm_token)
    if not sent:
        # Avoid trapping users in a pending state when email delivery fails.
        remove_unconfirmed_subscriber(email, confirm_token, tenant_id=tid)
        return JSONResponse(
            status_code=503,
            content={
                "error": "Could not send confirmation email right now. Please try subscribing again in a moment.",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "message": "Please check your inbox to confirm your subscription.",
            "conflict": conflict,
        },
    )


@router.get("/newsletter/confirm")
async def newsletter_confirm(request: Request, token: str = "") -> JSONResponse:
    """
    GET /api/newsletter/confirm?token=... – set confirmed_at (double opt-in).
    """
    if not token.strip():
        return JSONResponse(status_code=400, content={"error": "token is required"})
    confirmed = confirm_subscription(token)
    if not confirmed:
        return JSONResponse(
            status_code=404,
            content={"error": "Invalid or expired confirmation link, or already confirmed."},
        )
    synced = await upsert_subscribed_contact(confirmed["email"], confirmed["conflict"])
    if not synced:
        # Local subscription is valid; Resend Contacts sync failed (see logs).
        pass
    return JSONResponse(
        status_code=200,
        content={"message": "You're subscribed. You'll receive the daily briefing by email."},
    )


@router.get("/newsletter/unsubscribe")
async def newsletter_unsubscribe(request: Request, token: str = "") -> JSONResponse:
    """
    GET /api/newsletter/unsubscribe?token=... – remove subscriber.
    """
    if not token.strip():
        return JSONResponse(status_code=400, content={"error": "token is required"})
    ok, email_removed = remove_by_unsubscribe_token(token)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": "Invalid or expired unsubscribe link."},
        )
    if email_removed:
        await mark_contact_unsubscribed(email_removed)
    return JSONResponse(
        status_code=200,
        content={"message": "You have been unsubscribed."},
    )


async def run_daily_newsletter_job(app_state) -> tuple[list[str], int, bool]:
    """
    Run analysis for each conflict that has confirmed subscribers, then send daily briefing emails.
    Returns (conflicts, emails_sent, skipped_duplicate).

    Optional daily mutex (NEWSLETTER_DAILY_DEDUPE): one completed run per UTC calendar day to avoid
    duplicate mail when both in-process scheduler and external cron call this endpoint.
    """
    conflicts = get_conflicts_with_subscribers()
    if not conflicts:
        return ([], 0, False)

    acquired_lock = False
    if _NEWSLETTER_DAILY_DEDUPE:
        if not try_acquire_daily_newsletter_lock():
            return (conflicts, 0, True)
        acquired_lock = True

    state = app_state.state_service if hasattr(app_state, "state_service") else None
    loop = asyncio.get_running_loop()
    sent_total = 0
    sem = asyncio.Semaphore(_NEWSLETTER_SEND_PARALLELISM)

    def _run_analyze_default(c: str) -> Any:
        tid = get_default_tenant_id()
        ctx = RequestContext(tenant_id=tid, user_id=None, role="viewer", auth_method="default")
        tok = set_request_context(ctx)
        try:
            return analyze_conflict(c)
        finally:
            reset_request_context(tok)

    ntid = get_default_tenant_id()
    for conflict in conflicts:
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda c=conflict: _run_analyze_default(c)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue
        at_ts = time.time()
        if state:
            attach_pattern_flags(state, conflict, result, tenant_id=ntid)
            state.set_cache(conflict, result, at_ts, tenant_id=ntid)
        else:
            app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
        push_escalation_timeline(app_state, conflict, at_ts, result, tenant_id=ntid)
        push_agent_status(app_state, result, tenant_id=ntid)
        push_run_history(app_state, conflict, at_ts, result, tenant_id=ntid)
        subscribers = list_confirmed_subscribers(conflict, tenant_id=None)

        async def _send_one(sub: dict, *, res: dict = result) -> bool:
            async with sem:
                return await send_daily_briefing(
                    sub["email"], sub["conflict"], res, sub["unsubscribe_token"]
                )

        results = await asyncio.gather(*[_send_one(sub) for sub in subscribers], return_exceptions=True)
        for r in results:
            if r is True:
                sent_total += 1
            elif isinstance(r, Exception):
                logger.warning("Newsletter send task error: %s", r)

    # Only mark the UTC day complete if at least one email was sent. Otherwise the lock would
    # block retries even when analyze_conflict timed out for every conflict or all Resend calls failed.
    if _NEWSLETTER_DAILY_DEDUPE and acquired_lock:
        if sent_total > 0:
            mark_daily_newsletter_completed()
        else:
            clear_daily_newsletter_lock_today()
            logger.warning(
                "Newsletter daily: 0 emails sent for conflicts=%s (analysis timeout, send failure, or no confirmed subscribers). "
                "Lock cleared so send-daily / cron can retry today.",
                conflicts,
            )

    return (conflicts, sent_total, False)


@router.get("/newsletter/status")
@limiter.limit("30/minute")
async def newsletter_status(
    request: Request,
    x_newsletter_secret: str | None = Header(default=None, alias="X-Newsletter-Secret"),
) -> JSONResponse:
    """
    GET /api/newsletter/status – subscriber counts (confirmed vs pending) and DB backend/path.
    Same auth as send-daily: NEWSLETTER_CRON_SECRET via X-Newsletter-Secret when set.
    """
    secret = (os.getenv("NEWSLETTER_CRON_SECRET") or "").strip()
    if secret and x_newsletter_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Newsletter-Secret"})
    return JSONResponse(status_code=200, content=get_subscriber_stats())


@router.post("/newsletter/sync-from-resend")
@limiter.limit("5/minute")
async def newsletter_sync_from_resend(
    request: Request,
    body: SyncFromResendBody,
    x_newsletter_secret: str | None = Header(default=None, alias="X-Newsletter-Secret"),
) -> JSONResponse:
    """
    POST /api/newsletter/sync-from-resend – list contacts in a Resend segment and mirror into the subscriber store.

    - unsubscribed=false → insert confirmed row or confirm pending / update conflict (from Resend first_name).
    - unsubscribed=true → remove local row (aligns DB with “not subscribed” in Resend).

    Same auth as send-daily. Requires segment_id in body or RESEND_NEWSLETTER_SEGMENT_ID / RESEND_AUDIENCE_ID.
    """
    secret = (os.getenv("NEWSLETTER_CRON_SECRET") or "").strip()
    if secret and x_newsletter_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Newsletter-Secret"})
    segment_id = resolve_import_segment_id(body.segment_id)
    if not segment_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "segment_id required in JSON body or set RESEND_NEWSLETTER_SEGMENT_ID / RESEND_AUDIENCE_ID in env.",
            },
        )
    try:
        contacts = await fetch_contacts_from_resend(segment_id=segment_id)
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    counts: dict[str, int] = {"inserted": 0, "updated": 0, "removed": 0, "noop": 0}
    for c in contacts:
        if not isinstance(c, dict):
            continue
        email = c.get("email")
        if not email or not isinstance(email, str):
            continue
        unsubscribed = bool(c.get("unsubscribed"))
        conflict = _conflict_from_resend_contact(c)
        outcome = apply_resend_contact_sync(email, conflict, unsubscribed=unsubscribed, tenant_id=str(get_default_tenant_id()))
        if outcome in counts:
            counts[outcome] += 1
    return JSONResponse(
        status_code=200,
        content={
            "message": "Resend subscriber sync complete.",
            "segment_id": segment_id,
            "fetched": len(contacts),
            **counts,
        },
    )


@router.post("/newsletter/send-daily")
async def newsletter_send_daily(
    request: Request,
    x_newsletter_secret: str | None = Header(default=None, alias="X-Newsletter-Secret"),
) -> JSONResponse:
    """
    POST /api/newsletter/send-daily – run analysis for conflicts with subscribers, then send daily emails.
    Protected by NEWSLETTER_CRON_SECRET (header X-Newsletter-Secret).
    """
    secret = (os.getenv("NEWSLETTER_CRON_SECRET") or "").strip()
    if secret and x_newsletter_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Newsletter-Secret"})
    conflicts, sent_total, skipped_dup = await run_daily_newsletter_job(request.app.state)
    if not conflicts:
        return JSONResponse(status_code=200, content={"message": "No subscribers.", "sent": 0})
    if skipped_dup:
        return JSONResponse(
            status_code=200,
            content={
                "message": "Daily run already completed today (deduplicated).",
                "conflicts": conflicts,
                "sent": 0,
                "skipped_duplicate": True,
            },
        )
    return JSONResponse(
        status_code=200,
        content={"message": "Daily run complete.", "conflicts": conflicts, "sent": sent_total},
    )
