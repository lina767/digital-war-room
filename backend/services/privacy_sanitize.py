from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import urlsplit, urlunsplit

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def mask_email(value: str) -> str:
    raw = (value or "").strip()
    if "@" not in raw:
        return raw
    local, _, domain = raw.partition("@")
    if not local:
        return f"***@{domain}"
    if len(local) == 1:
        shown = local
    elif len(local) == 2:
        shown = local[0] + "*"
    else:
        shown = local[:2] + "*" * max(1, len(local) - 2)
    return f"{shown}@{domain}"


def mask_emails_in_text(value: str) -> str:
    if not value:
        return value
    return _EMAIL_RE.sub(lambda m: mask_email(m.group(0)), value)


def redact_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return raw
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def pseudonymize(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    salt = os.getenv("AUDIT_HASH_SALT", "").strip()
    payload = f"{salt}:{raw}" if salt else raw
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

