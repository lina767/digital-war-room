"""
Input sanitization for user-supplied values before agent dispatch or storage.
Prevents injection, oversized payloads, and control characters.
"""

import re
from typing import Optional

# Conflict names: letters, digits, spaces, hyphens, slashes (e.g. "Gaza/Israel"), commas
CONFLICT_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-/,]+$")
CONFLICT_MAX_LEN = 80


def sanitize_conflict(value: Optional[str]) -> str:
    """
    Sanitize a conflict identifier from query/path/body.
    Returns normalized string; raises ValueError if invalid.
    """
    if value is None:
        raise ValueError("conflict is required")
    s = (value or "").strip()
    if not s:
        raise ValueError("conflict cannot be empty")
    if len(s) > CONFLICT_MAX_LEN:
        raise ValueError(f"conflict longer than {CONFLICT_MAX_LEN} characters")
    # Reject control chars and null bytes
    if any(ord(c) < 32 and c not in "\t\n\r" for c in s):
        raise ValueError("conflict contains invalid characters")
    if "\x00" in s:
        raise ValueError("conflict contains invalid characters")
    if not CONFLICT_PATTERN.match(s):
        raise ValueError("conflict allows only letters, digits, spaces, hyphens, slashes, commas")
    return s
