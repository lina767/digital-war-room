"""Optional Resend email when an alert rule fires."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_rule_match_email(
    *,
    to_email: str,
    rule_name: str,
    conflict: str,
    title: str,
    body: str,
) -> bool:
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        logger.debug("RESEND_API_KEY not set; skip alert email")
        return False
    from_email = (os.getenv("RESEND_FROM_EMAIL") or os.getenv("NEWSLETTER_FROM_EMAIL") or "").strip()
    if not from_email:
        logger.warning("No RESEND_FROM_EMAIL / NEWSLETTER_FROM_EMAIL; skip alert email")
        return False
    try:
        import httpx

        payload = {
            "from": from_email,
            "to": [to_email],
            "subject": title[:200],
            "text": f"{body}\n\n— Digital War Room alert rule: {rule_name}\nConflict: {conflict}",
        }
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("Resend alert email failed: %s %s", r.status_code, r.text[:500])
            return False
        return True
    except Exception as e:
        logger.warning("send_rule_match_email error: %s", e)
        return False
