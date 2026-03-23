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
_RESEND_LIST_PAGE_SIZE = 100
DEFAULT_NEWSLETTER_CONFLICT = (os.getenv("NEWSLETTER_DEFAULT_CONFLICT") or "Global").strip() or "Global"


def _api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or "").strip()


def _audience_id() -> str:
    """Audience ID is required for all contact operations."""
    return (os.getenv("RESEND_AUDIENCE_ID") or "").strip()


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


def resolve_import_segment_id(explicit: str | None) -> str | None:
    """Prefer explicit segment UUID from caller; otherwise first ID from env (segment or legacy audience)."""
    s = (explicit or "").strip()
    if s:
        return s
    ids = _newsletter_segment_ids()
    return ids[0] if ids else None


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
    return await _upsert_contact(
        email=email,
        conflict=(conflict or DEFAULT_NEWSLETTER_CONFLICT),
        unsubscribed=True,
    )


async def _upsert_contact(email: str, conflict: str, unsubscribed: bool) -> bool:
    """
    Upsert contact into the configured audience.
    """
    if not contacts_sync_enabled():
        return True

    audience_id = _audience_id()
    if not audience_id:
        logger.warning("Resend contacts sync skipped: RESEND_AUDIENCE_ID not set")
        return True

    e = (email or "").strip().lower()
    if not e:
        return True

    key = _api_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    body: dict[str, Any] = {
        "email": e,
        "unsubscribed": unsubscribed,
        "first_name": conflict,  # Stores conflict as first_name.
    }

    client = get_http_client()

    try:
        # Correct endpoint: /audiences/{audience_id}/contacts
        resp = await client.request(
            "POST",
            f"{RESEND_API_BASE}/audiences/{audience_id}/contacts",
            headers=headers,
            json=body,
        )
        if 200 <= resp.status_code < 300:
            logger.info("Resend contact created for %s", e)
            return True

        if resp.status_code in (400, 409, 422):
            # Contact already exists - treat as success.
            logger.info("Resend contact exists for %s: %s", e, resp.text[:200])
            return True

        logger.warning("Resend contact failed status=%s body=%s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.exception("Resend contact upsert failed: %s", exc)
        return False


async def fetch_contacts_from_resend(*, segment_id: str | None = None) -> list[dict[str, Any]]:
    """
    List all contacts from Resend (GET /contacts) with cursor pagination.
    Optional segment_id filters to contacts in that segment (Resend query param).

    Raises RuntimeError on transport error or non-200 response.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("RESEND_API_KEY is not set")

    client = get_http_client()
    headers = {"Authorization": f"Bearer {key}"}
    all_rows: list[dict[str, Any]] = []
    after: str | None = None
    seg = (segment_id or "").strip() or None

    while True:
        params: dict[str, Any] = {"limit": _RESEND_LIST_PAGE_SIZE}
        if seg:
            params["segment_id"] = seg
        if after:
            params["after"] = after
        resp = await client.request("GET", f"{RESEND_API_BASE}/contacts", headers=headers, params=params)
        if resp.status_code != 200:
            logger.warning("Resend list contacts failed status=%s body=%s", resp.status_code, resp.text[:500])
            raise RuntimeError(f"Resend list contacts failed: HTTP {resp.status_code}")
        payload = resp.json()
        data = payload.get("data") or []
        if not isinstance(data, list):
            break
        for item in data:
            if isinstance(item, dict):
                all_rows.append(item)
        if not payload.get("has_more"):
            break
        if not data:
            break
        last_id = data[-1].get("id") if isinstance(data[-1], dict) else None
        if not last_id:
            break
        after = str(last_id)

    return all_rows


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


