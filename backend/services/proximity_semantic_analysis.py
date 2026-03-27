import json
import re
from typing import Any, Dict

from services.gemini_service import run_gemini_research


def _keyword_fallback(description: str) -> Dict[str, Any]:
    text = (description or "").lower()
    if not text:
        return {"event_type": "unknown", "intensity": 0.2, "confidence": 0.3, "rationale": "empty_description"}
    if re.search(r"artiller|heavy shell|barrage|rocket salvo", text):
        return {"event_type": "area_bombardment", "intensity": 0.92, "confidence": 0.75, "rationale": "area_fire_keywords"}
    if re.search(r"precision|single room|targeted strike|surgical", text):
        return {"event_type": "precision_strike", "intensity": 0.45, "confidence": 0.72, "rationale": "precision_keywords"}
    if re.search(r"drone|uav", text):
        return {"event_type": "drone_strike", "intensity": 0.62, "confidence": 0.68, "rationale": "drone_keywords"}
    return {"event_type": "kinetic_unknown", "intensity": 0.58, "confidence": 0.45, "rationale": "generic_kinetic_text"}


async def analyze_event_description(description: str) -> Dict[str, Any]:
    """Classify event semantics from unstructured description for risk weighting."""
    desc = (description or "").strip()
    if not desc:
        return _keyword_fallback(desc)
    schema_hint = {
        "event_type": "precision_strike | area_bombardment | drone_strike | unknown",
        "intensity": "0.0-1.0",
        "confidence": "0.0-1.0",
        "rationale": "short string",
    }
    prompt = (
        "Classify the military event description for collateral-risk modeling. "
        "Return strict JSON object only.\n"
        f"Schema: {json.dumps(schema_hint)}\n"
        f"Description: {desc[:1200]}"
    )
    result = run_gemini_research(prompt)
    if result.ok and isinstance(result.parsed_json, dict):
        parsed = result.parsed_json
        return {
            "event_type": str(parsed.get("event_type") or "unknown")[:64],
            "intensity": max(0.0, min(1.0, float(parsed.get("intensity") or 0.0))),
            "confidence": max(0.0, min(1.0, float(parsed.get("confidence") or 0.0))),
            "rationale": str(parsed.get("rationale") or "")[:240],
        }
    return _keyword_fallback(desc)
