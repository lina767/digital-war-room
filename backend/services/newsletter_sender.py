"""
Newsletter email sending via Resend. Confirmation (double opt-in) and daily briefing emails. All copy in English.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlencode

from services.email_templates import (
    confirmation_email_html,
    confirmation_email_text,
    daily_briefing_email_html,
    daily_briefing_email_text,
)
from services.http_client import get_http_client

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _is_configured() -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    return bool(key and _is_valid_from_address(from_addr))


def _missing_config_reasons() -> list[str]:
    reasons: list[str] = []
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    if not key:
        reasons.append("RESEND_API_KEY missing")
    if not from_addr:
        reasons.append("NEWSLETTER_FROM missing")
    elif not _is_valid_from_address(from_addr):
        reasons.append("NEWSLETTER_FROM invalid format")
    return reasons


def _is_valid_from_address(from_addr: str) -> bool:
    """
    Lightweight sender validation for Resend payload.
    Expected shape: local-part@domain.tld
    """
    if "@" not in from_addr:
        return False
    local, domain = from_addr.split("@", 1)
    if not local or not domain:
        return False
    return "." in domain


def _base_url() -> str:
    """Frontend base URL for confirm/unsubscribe and briefing links."""
    url = (os.getenv("FRONTEND_URL") or os.getenv("NEWSLETTER_BASE_URL") or "").strip()
    if url:
        return url.rstrip("/")
    return "https://digitalwarroom.com"


def _confirm_link(confirm_token: str) -> str:
    return f"{_base_url()}/newsletter/confirm?{urlencode({'token': confirm_token})}"


def _unsubscribe_link(unsubscribe_token: str) -> str:
    return f"{_base_url()}/newsletter/unsubscribe?{urlencode({'token': unsubscribe_token})}"


def _briefing_link(conflict: str) -> str:
    return f"{_base_url()}/daily-briefing?{urlencode({'conflict': conflict})}"


async def send_confirmation_email(email: str, conflict: str, confirm_token: str) -> bool:
    """
    Send double opt-in confirmation email. Link points to frontend /newsletter/confirm?token=...
    Returns True if sent successfully.
    """
    if not _is_configured():
        logger.warning("Newsletter: confirmation email skipped (%s)", ", ".join(_missing_config_reasons()))
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    link = _confirm_link(confirm_token)
    subject = "Confirm your Daily Briefing subscription"
    html = confirmation_email_html(conflict, link)
    text = confirmation_email_text(conflict, link)
    return await _send(email, subject, html, text, from_addr)


async def send_daily_briefing(email: str, conflict: str, briefing_data: Dict[str, Any], unsubscribe_token: str) -> bool:
    """
    Send daily briefing email. briefing_data: summary, key_findings (list), escalation_score, etc.
    """
    if not _is_configured():
        logger.warning("Newsletter: daily briefing skipped (%s)", ", ".join(_missing_config_reasons()))
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Daily Briefing – {conflict} – {date_str}"
    summary = (briefing_data.get("summary") or "").strip() or "No summary available."
    key_findings = briefing_data.get("key_findings") or []
    view_link = _briefing_link(conflict)
    unsub_link = _unsubscribe_link(unsubscribe_token)
    html = daily_briefing_email_html(
        conflict=conflict,
        date_str=date_str,
        summary=summary,
        key_findings=key_findings,
        escalation_score=briefing_data.get("escalation_score"),
        view_link=view_link,
        unsubscribe_link=unsub_link,
    )
    text = daily_briefing_email_text(
        conflict=conflict,
        date_str=date_str,
        summary=summary,
        key_findings=key_findings,
        escalation_score=briefing_data.get("escalation_score"),
        view_link=view_link,
        unsubscribe_link=unsub_link,
    )
    return await _send(email, subject, html, text, from_addr)


async def _send(to: str, subject: str, html: str, text: str, from_addr: str) -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not key:
        logger.warning("Newsletter send skipped: RESEND_API_KEY missing")
        return False
    if not _is_valid_from_address(from_addr):
        logger.warning("Invalid NEWSLETTER_FROM format: %s", from_addr)
        return False
    client = get_http_client()
    try:
        resp = await client.request(
            "POST",
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"from": from_addr, "to": [to], "subject": subject, "html": html, "text": text},
        )
        if resp.status_code >= 200 and resp.status_code < 300:
            logger.info("Newsletter email sent to %s", to)
            return True
        logger.warning("Resend API error status=%s body=%s", resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.exception("Failed to send newsletter email: %s", e)
        return False
