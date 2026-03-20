"""
Resend Contacts API (Segments / Broadcast lists).

Resend deprecated "Audiences" in favour of Contacts + Segments; see:
https://resend.com/docs/api-reference/contacts/create-contact

We use the same RESEND_API_KEY as transactional email. Optional segment IDs put
confirmed subscribers into your newsletter segment for Broadcasts.

HTTP only (no resend PyPI package) to match newsletter_sender.py.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

from services.http_client import get_http_client

logger = logging.getLogger(__name__)

RESEND_API_BASE = "https://api.resend.com"


def _api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or "").strip()


def contacts_sync_enabled() -> bool:
    """Sync to Resend Contacts when API key is set and feature is not disabled."""
    if not _api_key():
        return False
    flag = (os.getenv("RESEND_CONTACTS_SYNC") or "true").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _newsletter_segment_ids() -> list[str]:
    """
    Segment UUIDs from env. Comma-separated RESEND_NEWSLETTER_SEGMENT_IDS or single
    RESEND_NEWSLETTER_SEGMENT_ID. Legacy: RESEND_AUDIENCE_ID (deprecated name in Resend UI).
    """
    raw = (os.getenv("RESEND_NEWSLETTER_SEGMENT_IDS") or "").strip()
    if not raw:
        raw = (os.getenv("RESEND_NEWSLETTER_SEGMENT_ID") or "").strip()
    if not raw:
        raw = (os.getenv("RESEND_AUDIENCE_ID") or "").strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _contact_path_suffix(email: str) -> str:
    """Path segment for contact by email (URL-encoded)."""
    return quote((email or "").strip().lower(), safe="")


async def upsert_pending_contact(email: str, conflict: str) -> bool:
    """
    Create or update contact during subscribe step (pending confirmation).
    Resend-style double opt-in keeps pending contacts unsubscribed=True.
    """
    return await _upsert_contact(email=email, conflict=conflict, unsubscribed=True)


async def upsert_subscribed_contact(email: str, conflict: str) -> bool:
    """
    Create or update a Resend contact after successful confirmation.
    """
    return await _upsert_contact(email=email, conflict=conflict, unsubscribed=False)


async def mark_contact_unsubscribed(email: str, conflict: str | None = None) -> bool:
    """
    Mark contact as unsubscribed on Resend (without deleting contact history).
    """
    return await _upsert_contact(email=email, conflict=conflict or "Iran", unsubscribed=True)


async def _upsert_contact(email: str, conflict: str, unsubscribed: bool) -> bool:
    """
    Upsert contact and attach configured segment(s).
    Returns True if sync ran successfully or was skipped (no API key).
    """
    if not contacts_sync_enabled():
        return True

    e = (email or "").strip().lower()
    c = (conflict or "Iran").strip() or "Iran"
    if not e:
        return True

    key = _api_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    body: dict[str, Any] = {
        "email": e,
        "unsubscribed": unsubscribed,
        "properties": {"conflict": c},
    }
    segment_ids = _newsletter_segment_ids()
    if segment_ids:
        body["segments"] = [{"id": sid} for sid in segment_ids]

    client = get_http_client()
    path_suffix = _contact_path_suffix(e)

    try:
        resp = await client.request(
            "POST",
            f"{RESEND_API_BASE}/contacts",
            headers=headers,
            json=body,
        )
        if resp.status_code >= 200 and resp.status_code < 300:
            logger.info("Resend contact upserted for %s (unsubscribed=%s)", e, unsubscribed)
            await _ensure_segments(client, headers, path_suffix, segment_ids)
            return True

        # Treat duplicate as upsert via PATCH + segment adds
        if resp.status_code in (400, 409, 422):
            logger.info(
                "Resend contact create returned %s for %s; attempting PATCH upsert. body=%s",
                resp.status_code,
                e,
                resp.text[:500],
            )
            patch_resp = await client.request(
                "PATCH",
                f"{RESEND_API_BASE}/contacts/{path_suffix}",
                headers=headers,
                json={
                    "unsubscribed": unsubscribed,
                    "properties": {"conflict": c},
                },
            )
            if patch_resp.status_code < 200 or patch_resp.status_code >= 300:
                logger.warning(
                    "Resend contact PATCH failed status=%s body=%s",
                    patch_resp.status_code,
                    patch_resp.text,
                )
                return False
            await _ensure_segments(client, headers, path_suffix, segment_ids)
            return True

        logger.warning("Resend contact create failed status=%s body=%s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.exception("Resend contact upsert failed: %s", exc)
        return False


async def _ensure_segments(client, headers: dict[str, str], path_suffix: str, segment_ids: list[str]) -> None:
    for sid in segment_ids:
        try:
            r = await client.request(
                "POST",
                f"{RESEND_API_BASE}/contacts/{path_suffix}/segments/{sid}",
                headers=headers,
            )
            if r.status_code >= 200 and r.status_code < 300:
                continue
            # Already in segment or similar
            if r.status_code in (409, 422):
                logger.debug("Resend segment add noop for contact path=%s segment=%s: %s", path_suffix, sid, r.text[:200])
                continue
            logger.warning(
                "Resend add contact to segment failed status=%s segment=%s body=%s",
                r.status_code,
                sid,
                r.text,
            )
        except Exception as exc:
            logger.warning("Resend add contact to segment exception segment=%s: %s", sid, exc)


