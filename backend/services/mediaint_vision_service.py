"""
Claude Vision for MEDIAINT — Sonnet multimodal analysis (not Haiku).

Uses ANTHROPIC_API_KEY. Separate from HAIKU_* limits/budget; cap with MEDIAINT_VISION_MAX_CALLS.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_OSINT_VISION_SYSTEM = """You support open-source intelligence (OSINT) analysts reviewing imagery from social channels and messaging apps.
Be precise and honest about uncertainty. Do not identify named individuals. Distinguish facts visible in the image from inference.
Output structured plain text with the exact section headers requested in the user message."""


def _vision_enabled() -> bool:
    if not (os.getenv("ANTHROPIC_API_KEY") or "").strip():
        return False
    v = (os.getenv("MEDIAINT_VISION_ENABLED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _vision_model() -> str:
    explicit = (os.getenv("MEDIAINT_VISION_MODEL") or "").strip()
    if explicit:
        return explicit
    try:
        from agents.llm import get_model_name

        return get_model_name("agent")
    except Exception:
        return "claude-haiku-4-5-20251001"


def _prepare_image_jpeg(data: bytes) -> Optional[Tuple[bytes, str]]:
    """Resize if huge; normalize to JPEG for efficient base64 payload."""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        im.load()
        if im.mode in ("RGBA", "P", "LA"):
            im = im.convert("RGB")
        elif im.mode != "RGB":
            im = im.convert("RGB")
        w, h = im.size
        max_side = int(os.getenv("MEDIAINT_VISION_MAX_SIDE", "2048"))
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=88, optimize=True)
        out = buf.getvalue()
        if len(out) > 4_500_000:
            logger.warning("MEDIAINT vision: JPEG still large (%d bytes), skipping API", len(out))
            return None
        return out, "image/jpeg"
    except Exception as e:
        logger.debug("MEDIAINT vision prepare image failed: %s", e)
        return None


def maybe_analyze_osint_image(
    image_bytes: bytes,
    *,
    conflict: str,
    provenance: str,
    exif: Optional[Dict[str, Any]] = None,
    calls_used: List[int],
    max_calls: int,
) -> Optional[str]:
    """
    If enabled and under call cap, send image to Claude (Sonnet) with OSINT prompt.
    ``calls_used`` is a single-element list used as a mutable counter (incremented only on API attempt).
    """
    if not _vision_enabled():
        return None
    if calls_used[0] >= max_calls:
        return None
    prepared = _prepare_image_jpeg(image_bytes)
    if not prepared:
        return None
    jpeg_bytes, media_type = prepared
    b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")

    exif_note = ""
    if exif:
        try:
            safe = {k: v for k, v in exif.items() if k in ("Make", "Model", "DateTime", "DateTimeOriginal", "GPSLatitude", "GPSLongitude")}
            if safe:
                exif_note = json.dumps(safe, ensure_ascii=False)[:400]
        except Exception:
            exif_note = ""

    user_instructions = f"""Analyze this image for OSINT value.

Theater / query context (may not match the image): {conflict or "unknown"}
Source / pipeline hint: {provenance or "unknown"}
Embedded metadata hint (may be stripped or wrong; do not treat as verified location/time): {exif_note or "none"}

Use exactly these sections and headers:

1) SCENE
2) VISIBLE_TEXT / OCR
3) EQUIPMENT / OBJECTS
4) DAMAGE / INFRASTRUCTURE
5) CONTEXTUAL ASSESSMENT

In CONTEXTUAL ASSESSMENT, briefly relate visible cues to plausible scenarios (e.g. urban blast damage, vehicle convoy, aircraft on apron). Label speculation as such.
If the image is non-photographic, a meme, UI screenshot only, or too low quality, say so and keep other sections short."""

    calls_used[0] += 1
    model = _vision_model()
    try:
        from anthropic import Anthropic

        client = Anthropic()
        max_tokens = int(os.getenv("MEDIAINT_VISION_MAX_TOKENS", "1400"))
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_OSINT_VISION_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64},
                        },
                        {"type": "text", "text": user_instructions},
                    ],
                }
            ],
        )
        parts: List[str] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                parts.append(getattr(block, "text", "") or "")
        text = "\n".join(parts).strip()
        return text or None
    except Exception as e:
        logger.warning("MEDIAINT Claude Vision failed (%s): %s", model, e)
        return None
