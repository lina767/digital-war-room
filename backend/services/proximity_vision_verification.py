import json
from typing import Any, Dict

from services.gemini_service import run_gemini_vision_json
from services.google_static_imagery import fetch_static_satellite_image


async def verify_facility_visual(
    facility_name: str,
    facility_type: str,
    facility_lat: float,
    facility_lon: float,
) -> Dict[str, Any]:
    """Verify if OSM tag plausibly matches visible structure in satellite imagery."""
    img_bytes, mime_type = await fetch_static_satellite_image(facility_lat, facility_lon)
    prompt_schema = {
        "supports_tag": "boolean",
        "alternative_class": "string",
        "confidence": "0.0-1.0",
        "notes": "string",
    }
    prompt = (
        "You are validating an OSM facility tag against a satellite image. "
        "Decide whether the visible site plausibly matches the tag.\n"
        f"Facility name: {facility_name}\n"
        f"OSM tag/type: {facility_type}\n"
        "Return strict JSON only with this schema:\n"
        f"{json.dumps(prompt_schema)}"
    )
    res = run_gemini_vision_json(prompt=prompt, image_bytes=img_bytes, mime_type=mime_type)
    if res.ok and isinstance(res.parsed_json, dict):
        out = res.parsed_json
        return {
            "supports_tag": bool(out.get("supports_tag")),
            "alternative_class": str(out.get("alternative_class") or "")[:120],
            "confidence": max(0.0, min(1.0, float(out.get("confidence") or 0.0))),
            "notes": str(out.get("notes") or "")[:400],
        }
    return {"supports_tag": None, "alternative_class": "", "confidence": 0.0, "notes": res.error or "vision_unavailable"}
