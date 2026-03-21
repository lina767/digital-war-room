"""
Newsletter routes: subscribe (double opt-in), confirm, unsubscribe, send-daily (cron).
All responses and behaviour follow docs/NEWSLETTER-SPEC.md.
"""

import asyncio
import logging
import os
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from agents.supervisor import analyze_conflict
from middleware.rate_limit import limiter
from services.newsletter_sender import send_confirmation_email, send_daily_briefing
from services.newsletter_store import (
    add_subscriber,
    confirm_subscription,
    get_conflicts_with_subscribers,
    list_confirmed_subscribers,
    mark_daily_newsletter_completed,
    remove_by_unsubscribe_token,
    remove_unconfirmed_subscriber,
    try_acquire_daily_newsletter_lock,
)
from services.resend_contacts import (
    mark_contact_unsubscribed,
    upsert_pending_contact,
    upsert_subscribed_contact,
)
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


@router.post("/newsletter/subscribe")
@limiter.limit("10/minute")
async def newsletter_subscribe(request: Request, body: SubscribeBody) -> JSONResponse:
    """
    POST /api/newsletter/subscribe – create unconfirmed subscriber and send confirmation email.
    """
    email = (body.email or "").strip().lower()
    conflict = (body.conflict or NEWSLETTER_DEFAULT_CONFLICT).strip() or NEWSLETTER_DEFAULT_CONFLICT
    try:
        conflict = sanitize_conflict(conflict)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "field": "conflict"})
    confirm_token, unsubscribe_token = add_subscriber(email, conflict)
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
        remove_unconfirmed_subscriber(email, confirm_token)
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

    Optional SQLite mutex (NEWSLETTER_DAILY_DEDUPE): one completed run per UTC calendar day to avoid
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

    for conflict in conflicts:
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda c=conflict: analyze_conflict(c)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue
        at_ts = time.time()
        if state:
            state.set_cache(conflict, result, at_ts)
        else:
            app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
        push_escalation_timeline(app_state, conflict, at_ts, result)
        push_agent_status(app_state, result)
        push_run_history(app_state, conflict, at_ts, result)
        subscribers = list_confirmed_subscribers(conflict)

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

    if _NEWSLETTER_DAILY_DEDUPE and acquired_lock:
        mark_daily_newsletter_completed()
    return (conflicts, sent_total, False)


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
