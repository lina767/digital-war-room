"""
Newsletter email sending via Resend. Confirmation (double opt-in) and daily briefing emails. All copy in English.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlencode

from services.http_client import get_http_client

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _is_configured() -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    return bool(key and from_addr)


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
        logger.warning("Newsletter: RESEND_API_KEY or NEWSLETTER_FROM not set, skipping confirmation email")
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    link = _confirm_link(confirm_token)
    subject = "Confirm your Daily Briefing subscription"
    html = f"""
    <p>You requested the Daily Briefing for <strong>{conflict}</strong>.</p>
    <p>Click the link below to confirm your subscription:</p>
    <p><a href="{link}">Confirm subscription</a></p>
    <p>If you did not request this, you can ignore this email.</p>
    <p style="color:#666;font-size:12px;">Digital War Room – Geopolitical intelligence briefings</p>
    """
    return await _send(email, subject, html, from_addr)


async def send_daily_briefing(email: str, conflict: str, briefing_data: Dict[str, Any], unsubscribe_token: str) -> bool:
    """
    Send daily briefing email. briefing_data: summary, key_findings (list), escalation_score, etc.
    """
    if not _is_configured():
        logger.warning("Newsletter: RESEND_API_KEY or NEWSLETTER_FROM not set, skipping daily briefing")
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Daily Briefing – {conflict} – {date_str}"
    summary = (briefing_data.get("summary") or "").strip() or "No summary available."
    key_findings = briefing_data.get("key_findings") or []
    findings_list = "\n".join(f"<li>{_escape_html(str(f))}</li>" for f in key_findings[:10])
    view_link = _briefing_link(conflict)
    unsub_link = _unsubscribe_link(unsubscribe_token)
    html = f"""
    <h2>Daily Briefing – {_escape_html(conflict)}</h2>
    <p><strong>Executive Summary</strong></p>
    <p>{_escape_html(summary)}</p>
    <p><strong>Key developments</strong></p>
    <ul>{findings_list}</ul>
    <p><a href="{view_link}">View full briefing online</a></p>
    <hr style="margin-top:24px;border:none;border-top:1px solid #eee;">
    <p style="color:#666;font-size:12px;">
      You received this because you subscribed to the Daily Briefing.
      <a href="{unsub_link}">Unsubscribe</a>.
    </p>
    """
    return await _send(email, subject, html, from_addr)


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


async def _send(to: str, subject: str, html: str, from_addr: str) -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not key:
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
            json={"from": from_addr, "to": [to], "subject": subject, "html": html},
        )
        if resp.status_code >= 200 and resp.status_code < 300:
            logger.info("Newsletter email sent to %s", to)
            return True
        logger.warning("Resend API error %s: %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.exception("Failed to send newsletter email: %s", e)
        return False
