"""
Resend webhook receiver (Svix-signed). Handles bounce/complaint events to remove local subscribers and sync Contacts.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.newsletter_store import remove_subscriber_by_email
from services.resend_contacts import mark_contact_unsubscribed

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_recipient_emails(payload: dict[str, Any]) -> list[str]:
    """Best-effort extraction of recipient addresses from Resend webhook JSON."""
    out: list[str] = []
    data = payload.get("data")
    if not isinstance(data, dict):
        return out
    to_val = data.get("to")
    if isinstance(to_val, list):
        for x in to_val:
            if isinstance(x, str) and "@" in x:
                out.append(x.strip().lower())
    elif isinstance(to_val, str) and "@" in to_val:
        out.append(to_val.strip().lower())
    # Some payloads nest bounce info
    bounce = data.get("bounce") if isinstance(data.get("bounce"), dict) else {}
    for key in ("email", "recipient"):
        v = bounce.get(key) or data.get(key)
        if isinstance(v, str) and "@" in v:
            out.append(v.strip().lower())
    # Dedupe
    seen: set[str] = set()
    deduped: list[str] = []
    for e in out:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped


def _should_unsubscribe(event_type: str) -> bool:
    t = (event_type or "").lower()
    return any(
        x in t
        for x in (
            "email.bounced",
            "email.complained",
            "bounced",
            "complained",
        )
    )


@router.post("/webhooks/resend")
async def resend_webhook(request: Request) -> JSONResponse:
    """
    POST /api/webhooks/resend — Resend events (email.bounced, email.complained, …).
    Set RESEND_WEBHOOK_SECRET to the signing secret from the Resend dashboard (Svix).
    """
    secret = (os.getenv("RESEND_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return JSONResponse(status_code=503, content={"error": "RESEND_WEBHOOK_SECRET not configured"})

    raw = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id") or "",
        "svix-timestamp": request.headers.get("svix-timestamp") or "",
        "svix-signature": request.headers.get("svix-signature") or "",
    }

    try:
        from svix.webhooks import Webhook

        wh = Webhook(secret)
        payload = wh.verify(raw, headers)
    except Exception as e:
        logger.warning("Resend webhook verify failed: %s", e)
        return JSONResponse(status_code=400, content={"error": "invalid webhook signature"})

    if not isinstance(payload, dict):
        return JSONResponse(status_code=200, content={"ok": True, "ignored": True})

    event_type = str(payload.get("type") or "")
    if not _should_unsubscribe(event_type):
        return JSONResponse(status_code=200, content={"ok": True, "ignored": True, "type": event_type})

    emails = _extract_recipient_emails(payload)
    removed = 0
    for email in emails:
        if remove_subscriber_by_email(email):
            removed += 1
            try:
                await mark_contact_unsubscribed(email)
            except Exception as ex:
                logger.debug("Resend contact unsubscribe sync failed for %s: %s", email, ex)

    if emails:
        logger.info(
            "Resend webhook %s: processed recipients=%s removed_local=%d",
            event_type,
            emails,
            removed,
        )

    return JSONResponse(
        status_code=200,
        content={"ok": True, "type": event_type, "emails": emails, "removed": removed},
    )
