"""
Newsletter email sending via Resend. Confirmation (double opt-in) and daily briefing emails. All copy in English.

Retries with backoff on 429/5xx; List-Unsubscribe on daily mail; structured logging with Resend message id.
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from services.email_templates import (
    confirmation_email_html,
    confirmation_email_text,
    daily_briefing_email_html,
    daily_briefing_email_text,
)

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
# Resend / rate-limit courtesy: retries with jitter
_NEWSLETTER_SEND_MAX_RETRIES = max(1, min(8, int(os.getenv("NEWSLETTER_SEND_MAX_RETRIES", "4"))))
_NEWSLETTER_SEND_BACKOFF_BASE = float(os.getenv("NEWSLETTER_SEND_BACKOFF_BASE", "0.75"))


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
    Expected shape: local-part@domain.tld (deliverability: verify this domain in Resend and set SPF/DKIM).
    """
    if "@" not in from_addr:
        return False
    local, domain = from_addr.split("@", 1)
    if not local or not domain:
        return False
    return "." in domain


def log_newsletter_deliverability_hints() -> None:
    """
    Log once at startup: operational checklist for inbox placement (DNS is not verifiable from code).
    """
    if not _is_configured():
        return
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    domain = from_addr.split("@", 1)[1] if "@" in from_addr else "?"
    logger.info(
        "Newsletter deliverability: ensure domain %s is verified in Resend (SPF/DKIM); "
        "prefer a subdomain for NEWSLETTER_FROM; see docs/NEWSLETTER-SPEC.md",
        domain,
    )


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


def _briefing_link(_conflict: str) -> str:
    """Frontend Daily Briefing page is Iran-only; URL has no conflict selector."""
    return f"{_base_url()}/daily-briefing"


def _mask_email(addr: str) -> str:
    s = (addr or "").strip().lower()
    if "@" not in s:
        return "***"
    local, _, rest = s.partition("@")
    if len(local) <= 2:
        return f"**@{rest}"
    return f"{local[:2]}***@{rest}"


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
    return await _send(
        email,
        subject,
        html,
        text,
        from_addr,
        list_unsubscribe_url=None,
        conflict_for_log=conflict,
    )


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
        briefing_data=briefing_data,
        threat_level=briefing_data.get("threat_level"),
        key_findings_context=briefing_data.get("key_findings_context"),
    )
    text = daily_briefing_email_text(
        conflict=conflict,
        date_str=date_str,
        summary=summary,
        key_findings=key_findings,
        escalation_score=briefing_data.get("escalation_score"),
        view_link=view_link,
        unsubscribe_link=unsub_link,
        briefing_data=briefing_data,
        threat_level=briefing_data.get("threat_level"),
        key_findings_context=briefing_data.get("key_findings_context"),
    )
    return await _send(
        email,
        subject,
        html,
        text,
        from_addr,
        list_unsubscribe_url=unsub_link,
        conflict_for_log=conflict,
    )


def _parse_retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def _send(
    to: str,
    subject: str,
    html: str,
    text: str,
    from_addr: str,
    *,
    list_unsubscribe_url: Optional[str],
    conflict_for_log: Optional[str],
) -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not key:
        logger.warning("Newsletter send skipped: RESEND_API_KEY missing")
        return False
    if not _is_valid_from_address(from_addr):
        logger.warning("Invalid NEWSLETTER_FROM format: %s", from_addr)
        return False

    payload: Dict[str, Any] = {"from": from_addr, "to": [to], "subject": subject, "html": html, "text": text}
    if list_unsubscribe_url:
        # RFC 2369; angle-bracket HTTPS URL. Add RFC 8058 List-Unsubscribe-Post when POST /unsubscribe exists.
        payload["headers"] = [{"name": "List-Unsubscribe", "value": f"<{list_unsubscribe_url}>"}]

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        attempt = 0
        backoff = _NEWSLETTER_SEND_BACKOFF_BASE
        while attempt < _NEWSLETTER_SEND_MAX_RETRIES:
            attempt += 1
            try:
                resp = await client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.RequestError as e:
                logger.warning("Newsletter Resend transport error (attempt %s/%s): %s", attempt, _NEWSLETTER_SEND_MAX_RETRIES, e)
                if attempt >= _NEWSLETTER_SEND_MAX_RETRIES:
                    logger.exception("Newsletter send failed after retries: %s", e)
                    return False
                await asyncio.sleep(backoff + random.uniform(0, 0.25))
                backoff *= 2
                continue

            if 200 <= resp.status_code < 300:
                resend_id = None
                try:
                    body = resp.json()
                    if isinstance(body, dict):
                        resend_id = body.get("id")
                except Exception:
                    pass
                logger.info(
                    "Newsletter email sent to=%s conflict=%s resend_id=%s",
                    _mask_email(to),
                    conflict_for_log or "",
                    resend_id or "",
                )
                return True

            if resp.status_code == 429 or resp.status_code >= 500:
                ra = _parse_retry_after_seconds(resp)
                wait = ra if ra is not None else backoff + random.uniform(0, 0.35)
                logger.warning(
                    "Resend API status=%s to=%s attempt=%s/%s wait=%.2fs body=%s",
                    resp.status_code,
                    _mask_email(to),
                    attempt,
                    _NEWSLETTER_SEND_MAX_RETRIES,
                    wait,
                    (resp.text or "")[:500],
                )
                if attempt >= _NEWSLETTER_SEND_MAX_RETRIES:
                    return False
                await asyncio.sleep(wait)
                backoff *= 2
                continue

            logger.warning("Resend API error status=%s to=%s body=%s", resp.status_code, _mask_email(to), resp.text[:800])
            return False

    return False
