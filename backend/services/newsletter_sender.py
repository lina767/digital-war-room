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
from urllib.parse import urlparse, urlencode

import httpx

from services.email_templates import (
    confirmation_email_html,
    confirmation_email_text,
)
from services.newsletter_content_templates import daily_briefing_email_html, daily_briefing_email_text
from services.newsletter_content_templates import (
    daily_briefing_digest_html,
    daily_briefing_digest_text,
)

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
# Resend / rate-limit courtesy: retries with jitter
_NEWSLETTER_SEND_MAX_RETRIES = max(1, min(8, int(os.getenv("NEWSLETTER_SEND_MAX_RETRIES", "4"))))
_NEWSLETTER_SEND_BACKOFF_BASE = float(os.getenv("NEWSLETTER_SEND_BACKOFF_BASE", "0.75"))
_NEWSLETTER_LAYOUT = (os.getenv("NEWSLETTER_LAYOUT") or "single").strip().lower()
_NEWSLETTER_WEEKLY_INFOGRAPHIC_ENABLED = (
    (os.getenv("NEWSLETTER_WEEKLY_INFOGRAPHIC_ENABLED", "false") or "").strip().lower() not in ("0", "false", "no")
)
_NEWSLETTER_WEEKLY_INFOGRAPHIC_WEEKDAY = max(
    0, min(6, int(os.getenv("NEWSLETTER_WEEKLY_INFOGRAPHIC_WEEKDAY", "0")))
)
_NEWSLETTER_INFOGRAPHIC_IMAGE_ENABLED = (
    (os.getenv("NEWSLETTER_INFOGRAPHIC_IMAGE_ENABLED", "true") or "").strip().lower() not in ("0", "false", "no")
)
_NEWSLETTER_INFOGRAPHIC_MODEL = (
    os.getenv("NEWSLETTER_INFOGRAPHIC_MODEL") or "gemini-3.1-flash-image-preview"
).strip()
_NEWSLETTER_INFOGRAPHIC_TIMEOUT_SEC = float(os.getenv("NEWSLETTER_INFOGRAPHIC_TIMEOUT_SEC", "45"))

_weekly_infographic_task_cache: dict[str, "asyncio.Task[Optional[str]]"] = {}
_weekly_infographic_task_lock = asyncio.Lock()


def _is_weekly_infographic_day(now_utc: datetime) -> bool:
    return _NEWSLETTER_WEEKLY_INFOGRAPHIC_ENABLED and now_utc.weekday() == _NEWSLETTER_WEEKLY_INFOGRAPHIC_WEEKDAY


def _build_weekly_infographic_prompt(conflict: str, date_str: str, briefing_data: Dict[str, Any]) -> str:
    summary = (briefing_data.get("summary") or "").strip()[:700]
    findings = briefing_data.get("key_findings") or []
    findings = [str(x).strip() for x in findings if str(x).strip()][:6]
    findings_block = "\n".join(f"- {item[:180]}" for item in findings) or "- No major findings available."
    threat = str(briefing_data.get("threat_level") or "ELEVATED").upper()
    escalation = briefing_data.get("escalation_score")
    esc_txt = f"{escalation}/100" if escalation is not None else "n/a"
    return (
        "Create a clean intelligence infographic in landscape format (16:9), editorial style, "
        "high contrast, minimal iconography, no logos.\n"
        f"Title: Weekly Intelligence Snapshot - {conflict}\n"
        f"Date: {date_str}\n"
        f"Threat level: {threat}\n"
        f"Escalation score: {esc_txt}\n"
        "Executive summary:\n"
        f"{summary or 'No summary available.'}\n"
        "Top findings:\n"
        f"{findings_block}\n"
        "Constraints: concise labels, modern dashboard aesthetic, no fake charts, "
        "no unreadable tiny text, no references to sources not provided."
    )


async def _generate_weekly_infographic_data_uri(
    *, conflict: str, date_str: str, briefing_data: Dict[str, Any]
) -> Optional[str]:
    if not _NEWSLETTER_INFOGRAPHIC_IMAGE_ENABLED:
        return None
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None
    api_base = (os.getenv("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{api_base}/models/{_NEWSLETTER_INFOGRAPHIC_MODEL}:generateContent?key={api_key}"
    prompt = _build_weekly_infographic_prompt(conflict, date_str, briefing_data)
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.35},
    }
    try:
        timeout = httpx.Timeout(_NEWSLETTER_INFOGRAPHIC_TIMEOUT_SEC)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Newsletter weekly infographic generation failed: %s", exc)
        return None

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content") if isinstance(first, dict) else {}
    parts = content.get("parts") if isinstance(content, dict) else []
    if not isinstance(parts, list):
        return None
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData") if isinstance(part.get("inlineData"), dict) else part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        raw = inline.get("data")
        if not isinstance(raw, str) or not raw.strip():
            continue
        mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
        return f"data:{mime};base64,{raw}"
    return None


async def _get_weekly_infographic_data_uri(
    *, conflict: str, date_str: str, briefing_data: Dict[str, Any]
) -> Optional[str]:
    key = f"{date_str}:{conflict.lower().strip()}"
    async with _weekly_infographic_task_lock:
        task = _weekly_infographic_task_cache.get(key)
        if task is None:
            task = asyncio.create_task(
                _generate_weekly_infographic_data_uri(
                    conflict=conflict,
                    date_str=date_str,
                    briefing_data=briefing_data,
                )
            )
            _weekly_infographic_task_cache[key] = task
    try:
        return await task
    except Exception:
        return None


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


def _normalize_base_url(value: str) -> str:
    """
    Normalize frontend base URL for email links.
    If scheme is missing, default to https:// to avoid malformed links in email clients.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return candidate.rstrip("/")


def _base_url() -> str:
    """Frontend base URL for confirm/unsubscribe and briefing links."""
    configured = _normalize_base_url(os.getenv("FRONTEND_URL") or os.getenv("NEWSLETTER_BASE_URL") or "")
    if configured:
        return configured
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


async def send_confirmation_email(email: str, conflict: str, confirm_token: str, *, reminder: bool = False) -> bool:
    """
    Send double opt-in confirmation email. Link points to frontend /newsletter/confirm?token=...
    Returns True if sent successfully.
    """
    if not _is_configured():
        logger.warning("Newsletter: confirmation email skipped (%s)", ", ".join(_missing_config_reasons()))
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    link = _confirm_link(confirm_token)
    subject = "Reminder: confirm your Daily Briefing subscription" if reminder else "Confirm your Daily Briefing subscription"
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


async def send_daily_briefing(
    email: str,
    conflict: str,
    briefing_data: Dict[str, Any],
    unsubscribe_token: str,
    *,
    force_weekly_infographic: bool = False,
) -> bool:
    """
    Send daily briefing email. briefing_data: summary, key_findings (list), escalation_score, etc.
    """
    if not _is_configured():
        logger.warning("Newsletter: daily briefing skipped (%s)", ", ".join(_missing_config_reasons()))
        return False
    from_addr = (os.getenv("NEWSLETTER_FROM") or "").strip()
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")
    is_digest = _NEWSLETTER_LAYOUT == "digest"
    subject = (
        f"Daily Briefing Digest – {conflict} – {date_str}"
        if is_digest
        else f"Daily Briefing – {conflict} – {date_str}"
    )
    summary = (briefing_data.get("summary") or "").strip() or "No summary available."
    key_findings = briefing_data.get("key_findings") or []
    briefing_payload = dict(briefing_data or {})
    briefing_payload["_weekly_infographic_enabled"] = force_weekly_infographic or _is_weekly_infographic_day(now_utc)
    if briefing_payload["_weekly_infographic_enabled"]:
        briefing_payload["_weekly_infographic_data_uri"] = await _get_weekly_infographic_data_uri(
            conflict=conflict,
            date_str=date_str,
            briefing_data=briefing_payload,
        )
    view_link = _briefing_link(conflict)
    unsub_link = _unsubscribe_link(unsubscribe_token)
    if is_digest:
        html = daily_briefing_digest_html(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            view_link=view_link,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=briefing_payload.get("key_findings_context"),
        )
        text = daily_briefing_digest_text(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            view_link=view_link,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=briefing_payload.get("key_findings_context"),
        )
    else:
        html = daily_briefing_email_html(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            escalation_score=briefing_data.get("escalation_score"),
            view_link=view_link,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=briefing_payload.get("key_findings_context"),
        )
        text = daily_briefing_email_text(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            escalation_score=briefing_data.get("escalation_score"),
            view_link=view_link,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=briefing_payload.get("key_findings_context"),
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
