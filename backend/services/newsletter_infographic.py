"""
Newsletter infographic: compress inline images for email size limits (Gmail clipping).
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_MAX_PNG_BYTES = max(10240, int(os.getenv("NEWSLETTER_INFOGRAPHIC_MAX_IMAGE_BYTES", str(80 * 1024))))
_MAX_HTML_BYTES = max(51200, int(os.getenv("NEWSLETTER_MAX_HTML_BYTES", str(95 * 1024))))


def max_html_bytes() -> int:
    return _MAX_HTML_BYTES


def _split_data_uri(data_uri: str) -> Optional[Tuple[str, bytes]]:
    if not isinstance(data_uri, str) or not data_uri.startswith("data:"):
        return None
    try:
        head, b64 = data_uri.split(",", 1)
        mime = "image/png"
        if ";" in head:
            mime = head[5:].split(";")[0].strip() or mime
        raw = base64.b64decode(b64, validate=False)
        if not raw:
            return None
        return (mime, raw)
    except Exception:
        return None


def compress_data_uri_for_email(data_uri: str) -> Optional[str]:
    """
    Shrink inline image to stay under NEWSLETTER_INFOGRAPHIC_MAX_IMAGE_BYTES (decoded).
    Prefers JPEG for smaller payloads; returns data:image/jpeg;base64,... or None if unusable.
    """
    parsed = _split_data_uri(data_uri)
    if not parsed:
        return None
    _mime, raw = parsed
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not available; skipping infographic compression")
        return data_uri if len(raw) <= _MAX_PNG_BYTES else None

    try:
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
    except Exception as exc:
        logger.warning("Newsletter infographic decode failed: %s", exc)
        return None

    def try_save(img, size: Optional[Tuple[int, int]] = None) -> Optional[bytes]:
        work = img if size is None else img.resize(size, Image.Resampling.LANCZOS)
        for q in (88, 82, 76, 70, 64, 58, 52, 46, 40, 34):
            buf = io.BytesIO()
            work.save(buf, format="JPEG", quality=q, optimize=True)
            blob = buf.getvalue()
            if len(blob) <= _MAX_PNG_BYTES:
                return blob
        return None

    blob = try_save(im)
    w, h = im.size
    while blob is None and w > 320 and h > 180:
        w, h = max(320, int(w * 0.88)), max(180, int(h * 0.88))
        blob = try_save(im, (w, h))

    if blob is None:
        logger.warning(
            "Newsletter infographic still too large after compression (max %s bytes)",
            _MAX_PNG_BYTES,
        )
        return None
    b64 = base64.b64encode(blob).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def should_strip_infographic_from_html(html: str) -> bool:
    return len(html.encode("utf-8")) > _MAX_HTML_BYTES
