"""
Newsletter email sending via Resend. Confirmation (double opt-in) and daily briefing emails. All copy in English.

Retries with backoff on 429/5xx; List-Unsubscribe on daily mail; structured logging with Resend message id.
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, urlencode

import httpx

from services.email_templates import (
    confirmation_email_html,
    confirmation_email_text,
)
from services.newsletter_content_templates import (
    daily_briefing_digest_html,
    daily_briefing_digest_text,
    daily_briefing_email_html,
    daily_briefing_email_text,
    finding_display_order,
)
from services.newsletter_infographic import (
    compress_data_uri_for_email,
    max_html_bytes,
    should_strip_infographic_from_html,
)
from services.newsletter_link_builder import (
    build_newsletter_link_bundle,
    digest_row_url,
    utm_campaign_for_date,
)
from services.resend_template_payloads import (
    build_confirmation_template_variables,
    build_daily_briefing_template_variables,
    data_uri_to_inline_attachment,
)

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
# Resend / rate-limit courtesy: retries with jitter
_NEWSLETTER_SEND_MAX_RETRIES = max(1, min(8, int(os.getenv("NEWSLETTER_SEND_MAX_RETRIES", "4"))))
_NEWSLETTER_SEND_BACKOFF_BASE = float(os.getenv("NEWSLETTER_SEND_BACKOFF_BASE", "0.75"))
_NEWSLETTER_LAYOUT = (os.getenv("NEWSLETTER_LAYOUT") or "single").strip().lower()
_NEWSLETTER_INFOGRAPHIC_ALWAYS = (
    (os.getenv("NEWSLETTER_INFOGRAPHIC_ALWAYS", "true") or "").strip().lower() not in ("0", "false", "no")
)
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


def _resend_template_id_confirm() -> str:
    return (os.getenv("RESEND_TEMPLATE_ID_CONFIRM") or "").strip()


def _resend_template_id_daily() -> str:
    return (os.getenv("RESEND_TEMPLATE_ID_DAILY") or "").strip()


_daily_infographic_task_cache: dict[str, "asyncio.Task[Optional[str]]"] = {}
_daily_infographic_task_lock = asyncio.Lock()


def newsletter_campaign_date_str(now_utc: Optional[datetime] = None) -> str:
    """
    Calendar date (YYYY-MM-DD) in NEWSLETTER_SEND_TIMEZONE for subject lines, UTM campaign, and infographic cache keys.
    """
    dt = now_utc or datetime.now(timezone.utc)
    tz_name = (os.getenv("NEWSLETTER_SEND_TIMEZONE") or "Europe/Berlin").strip() or "Europe/Berlin"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def _is_weekly_infographic_day(now_utc: datetime) -> bool:
    return _NEWSLETTER_WEEKLY_INFOGRAPHIC_ENABLED and now_utc.weekday() == _NEWSLETTER_WEEKLY_INFOGRAPHIC_WEEKDAY


def _infographic_enabled_for_send(now_utc: datetime, *, force: bool) -> bool:
    if force:
        return True
    if _NEWSLETTER_INFOGRAPHIC_ALWAYS:
        return True
    return _is_weekly_infographic_day(now_utc)


def _build_daily_infographic_prompt(conflict: str, date_str: str, briefing_data: Dict[str, Any]) -> str:
    summary = (briefing_data.get("summary") or "").strip()[:700]
    findings = briefing_data.get("key_findings") or []
    findings = [str(x).strip() for x in findings if str(x).strip()][:6]
    findings_block = "\n".join(f"- {item[:180]}" for item in findings) or "- No major findings available."
    threat = str(briefing_data.get("threat_level") or "ELEVATED").upper()
    escalation = briefing_data.get("escalation_score")
    esc_txt = f"{escalation}/100" if escalation is not None else "n/a"
    return (
        "Create a clean intelligence infographic in landscape format (16:9), editorial style, "
        "high contrast, minimal iconography, no logos. Use a light neutral background with dark text "
        "so the graphic stays readable if email clients apply dark mode color inversion.\n"
        f"Title: Daily Intelligence Snapshot - {conflict}\n"
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


async def _generate_daily_infographic_data_uri(
    *, conflict: str, date_str: str, briefing_data: Dict[str, Any]
) -> Optional[str]:
    if not _NEWSLETTER_INFOGRAPHIC_IMAGE_ENABLED:
        return None
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None
    api_base = (os.getenv("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{api_base}/models/{_NEWSLETTER_INFOGRAPHIC_MODEL}:generateContent?key={api_key}"
    prompt = _build_daily_infographic_prompt(conflict, date_str, briefing_data)
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
        logger.warning("Newsletter daily infographic generation failed: %s", exc)
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
        data_uri = f"data:{mime};base64,{raw}"
        compressed = compress_data_uri_for_email(data_uri)
        return compressed or data_uri
    return None


async def _get_daily_infographic_data_uri(
    *, conflict: str, date_str: str, briefing_data: Dict[str, Any]
) -> Optional[str]:
    key = f"{date_str}:{conflict.lower().strip()}"
    async with _daily_infographic_task_lock:
        task = _daily_infographic_task_cache.get(key)
        if task is None:
            task = asyncio.create_task(
                _generate_daily_infographic_data_uri(
                    conflict=conflict,
                    date_str=date_str,
                    briefing_data=briefing_data,
                )
            )
            _daily_infographic_task_cache[key] = task
    try:
        return await task
    except Exception:
        return None


async def attach_daily_infographic_to_briefing(
    briefing_data: Dict[str, Any],
    conflict: str,
    date_str: str,
    *,
    force: bool = False,
) -> None:
    """
    Mutates briefing_data: sets _newsletter_infographic_enabled and optional _newsletter_infographic_data_uri.
    Call before caching analysis so the web Daily Briefing can show the same asset.
    """
    now_utc = datetime.now(timezone.utc)
    enabled = _infographic_enabled_for_send(now_utc, force=force)
    briefing_data["_newsletter_infographic_enabled"] = enabled
    if not enabled:
        return
    if (briefing_data.get("_newsletter_infographic_data_uri") or "").strip().startswith("data:image/"):
        return
    uri = await _get_daily_infographic_data_uri(
        conflict=conflict,
        date_str=date_str,
        briefing_data=briefing_data,
    )
    if uri:
        briefing_data["_newsletter_infographic_data_uri"] = uri


def _attach_tracked_links(
    briefing_payload: Dict[str, Any],
    *,
    conflict: str,
    date_str: str,
    key_findings: list,
    order_indices: list[int],
) -> None:
    base = _base_url()
    bundle = build_newsletter_link_bundle(
        base_url=base,
        conflict=conflict,
        date_str=date_str,
        key_findings=list(key_findings or []),
        finding_display_indices=order_indices[:5],
    )
    briefing_payload["_nl_bluf_cta"] = bundle["bluf_cta"]
    briefing_payload["_nl_infographic_cta"] = bundle["infographic_cta"]
    briefing_payload["_nl_view_full"] = bundle["view_full"]
    briefing_payload["_nl_finding_urls"] = bundle["finding_urls"]
    briefing_payload["_nl_public_fallback"] = bundle["public_briefing_fallback"]
    campaign = utm_campaign_for_date(date_str)
    params_common = {
        "campaign": campaign,
        "utm_content": "feedback",
        "conflict": conflict,
    }
    useful_qs = urlencode({**params_common, "kind": "useful"})
    not_useful_qs = urlencode({**params_common, "kind": "not_useful"})
    briefing_payload["_nl_feedback_useful"] = f"{base}/api/newsletter/feedback?{useful_qs}"
    briefing_payload["_nl_feedback_not_useful"] = f"{base}/api/newsletter/feedback?{not_useful_qs}"


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
    tid = _resend_template_id_confirm()
    if tid:
        variables = build_confirmation_template_variables(conflict, link, reminder=reminder)
        return await _send(
            email,
            subject,
            from_addr,
            list_unsubscribe_url=None,
            conflict_for_log=conflict,
            template_id=tid,
            template_variables=variables,
        )
    html = confirmation_email_html(conflict, link)
    text = confirmation_email_text(conflict, link)
    return await _send(
        email,
        subject,
        from_addr,
        list_unsubscribe_url=None,
        conflict_for_log=conflict,
        html=html,
        text=text,
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
    date_str = newsletter_campaign_date_str(now_utc)
    is_digest = _NEWSLETTER_LAYOUT == "digest"
    subject = (
        f"Ops Digest: what changed since yesterday – {conflict} – {date_str}"
        if is_digest
        else f"Ops Briefing: 3 shifts that changed risk – {conflict} – {date_str}"
    )
    summary = (briefing_data.get("summary") or "").strip() or "No summary available."
    key_findings = briefing_data.get("key_findings") or []
    briefing_payload = dict(briefing_data or {})

    infographic_on = _infographic_enabled_for_send(now_utc, force=force_weekly_infographic)
    briefing_payload["_newsletter_infographic_enabled"] = infographic_on
    if infographic_on:
        if not (briefing_payload.get("_newsletter_infographic_data_uri") or "").strip().startswith("data:image/"):
            briefing_payload["_newsletter_infographic_data_uri"] = await _get_daily_infographic_data_uri(
                conflict=conflict,
                date_str=date_str,
                briefing_data=briefing_payload,
            )

    kf = list(key_findings or [])
    conf_list = briefing_payload.get("key_findings_confidence")
    conf_list = conf_list if isinstance(conf_list, list) else []
    order = finding_display_order(kf, conf_list if len(conf_list) >= len(kf) else None)
    _attach_tracked_links(briefing_payload, conflict=conflict, date_str=date_str, key_findings=kf, order_indices=order)

    view_link = briefing_payload.get("_nl_view_full") or _briefing_link(conflict)
    unsub_link = _unsubscribe_link(unsubscribe_token)
    base = _base_url()
    digest_view = build_newsletter_link_bundle(
        base_url=base,
        conflict=conflict,
        date_str=date_str,
        key_findings=kf,
        finding_display_indices=order[:5],
    )["view_full"]
    row_count = len(briefing_payload.get("key_findings") or [])
    digest_row_links = [digest_row_url(base, date_str, i + 1) for i in range(min(50, row_count))]
    ctx_list = briefing_payload.get("key_findings_context")
    ctx_list = ctx_list if isinstance(ctx_list, list) else []

    if is_digest:
        html = daily_briefing_digest_html(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            view_link=digest_view,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=ctx_list,
            row_links=digest_row_links,
        )
        text = daily_briefing_digest_text(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            view_link=digest_view,
            unsubscribe_link=unsub_link,
            briefing_data=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            key_findings_context=ctx_list,
            row_links=digest_row_links,
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
            key_findings_context=ctx_list,
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
            key_findings_context=ctx_list,
        )

    if should_strip_infographic_from_html(html) and infographic_on:
        logger.warning(
            "Newsletter HTML exceeds %s bytes; stripping inline infographic for deliverability",
            max_html_bytes(),
        )
        briefing_payload["_newsletter_infographic_data_uri"] = ""
        briefing_payload["_newsletter_infographic_oversize"] = True
        if is_digest:
            html = daily_briefing_digest_html(
                conflict=conflict,
                date_str=date_str,
                summary=summary,
                key_findings=key_findings,
                view_link=digest_view,
                unsubscribe_link=unsub_link,
                briefing_data=briefing_payload,
                threat_level=briefing_payload.get("threat_level"),
                key_findings_context=ctx_list,
                row_links=digest_row_links,
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
                key_findings_context=ctx_list,
            )

    daily_tid = _resend_template_id_daily()
    if daily_tid and not is_digest:
        uri = (briefing_payload.get("_newsletter_infographic_data_uri") or "").strip()
        if briefing_payload.get("_newsletter_infographic_oversize"):
            uri = ""
        include_cid = bool(uri.startswith("data:image/"))
        att = data_uri_to_inline_attachment(uri) if include_cid else None
        variables = build_daily_briefing_template_variables(
            conflict=conflict,
            date_str=date_str,
            summary=summary,
            key_findings=key_findings,
            briefing_payload=briefing_payload,
            threat_level=briefing_payload.get("threat_level"),
            escalation_score=briefing_data.get("escalation_score"),
            unsubscribe_link=unsub_link,
            view_link=view_link,
            order_indices=order,
            key_findings_context=ctx_list,
            include_infographic_cid=include_cid,
        )
        return await _send(
            email,
            subject,
            from_addr,
            list_unsubscribe_url=unsub_link,
            conflict_for_log=conflict,
            template_id=daily_tid,
            template_variables=variables,
            attachments=[att] if att else None,
        )
    if daily_tid and is_digest:
        logger.info(
            "RESEND_TEMPLATE_ID_DAILY is set but daily digest layout uses inline HTML "
            "(Resend templates support at most 20 variables; digest not mapped). "
            "Unset RESEND_TEMPLATE_ID_DAILY or use NEWSLETTER_LAYOUT=single for template sends."
        )

    return await _send(
        email,
        subject,
        from_addr,
        list_unsubscribe_url=unsub_link,
        conflict_for_log=conflict,
        html=html,
        text=text,
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
    from_addr: str,
    *,
    list_unsubscribe_url: Optional[str],
    conflict_for_log: Optional[str],
    html: Optional[str] = None,
    text: Optional[str] = None,
    template_id: Optional[str] = None,
    template_variables: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not key:
        logger.warning("Newsletter send skipped: RESEND_API_KEY missing")
        return False
    if not _is_valid_from_address(from_addr):
        logger.warning("Invalid NEWSLETTER_FROM format: %s", from_addr)
        return False

    use_template = bool((template_id or "").strip() and template_variables is not None)
    if use_template:
        payload: Dict[str, Any] = {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "template": {"id": (template_id or "").strip(), "variables": template_variables or {}},
        }
    else:
        if html is None:
            html = ""
        if text is None:
            text = ""
        payload = {"from": from_addr, "to": [to], "subject": subject, "html": html, "text": text}
    if attachments:
        payload["attachments"] = [a for a in attachments if a]
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
