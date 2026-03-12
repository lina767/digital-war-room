"""
Shared utilities for all backend agents.
Eliminates duplication of common helpers across sigint, finint, geoint, news agents.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Type-safe conversions ─────────────────────────────────────────────────

def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """Convert to float, returning *default* on failure (None if not given)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── LLM response cleaning ────────────────────────────────────────────────

def strip_llm_json(text: str) -> str:
    """Remove ```json / ``` wrappers that LLMs add around JSON."""
    text = text.strip()
    for prefix in ("```json", "```"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    """Strip LLM markdown fences, parse JSON. Returns None on failure."""
    cleaned = strip_llm_json(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


# ── ADS-B response normalisation ─────────────────────────────────────────

def parse_adsb_response(data: Any) -> List[Dict[str, Any]]:
    """Normalise the various ADS-B JSON shapes into a flat aircraft list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("ac") or data.get("aircraft") or []
    return []


# ── Shared Pydantic models ───────────────────────────────────────────────

class ScoreConfidence(BaseModel):
    """Confidence metadata attached to every agent score."""
    level: str = "low"
    sources_ok: List[str] = Field(default_factory=list)
    sources_missing: List[str] = Field(default_factory=list)
