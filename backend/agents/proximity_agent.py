"""
PROXIMITY Agent – Strike–civilian infrastructure correlation (human-shield / collateral risk).
Uses NASA FIRMS thermal anomalies as strike triggers, Overpass (OSM) for schools/hospitals/government,
optional tunnel/military sites GeoJSON for PROBABLE_HUMAN_SHIELD. Runs in the same pipeline as
other agents; also available via GET /api/proximity/analyze and the Dashboard "Run" button.
"""
import asyncio
import os
from typing import Any, Dict, List

from agents.geoint_agent import get_thermal_anomalies
from services.proximity_correlation import run_correlation_for_events
from services.http_client import get_http_client

# Max strike events to correlate (Overpass rate limit; keep agent run time bounded)
MAX_STRIKES = 15

# Conflict name -> FIRMS region (same as GEOINT)
CONFLICT_TO_REGION = {
    "iran": "iran",
    "gaza": "gaza_israel",
    "israel": "gaza_israel",
    "lebanon": "middle_east",
    "yemen": "yemen",
    "syria": "middle_east",
    "iraq": "middle_east",
    "ukraine": "eastern_europe",
    "default": "middle_east",
}


def _conflict_to_region(conflict: str) -> str:
    cl = (conflict or "").lower()
    return next(
        (v for k, v in CONFLICT_TO_REGION.items() if k != "default" and k in cl),
        CONFLICT_TO_REGION["default"],
    )


def _compute_proximity_score(evidence: List[Dict[str, Any]]) -> float:
    """Score 0–100 from evidence risk labels (critical/human-shield weigh most)."""
    if not evidence:
        return 0.0
    total = 0.0
    for e in evidence:
        label = (e.get("riskLabel") or "").strip()
        if label == "CRITICAL_PROXIMITY":
            total += 28
        elif label == "PROBABLE_HUMAN_SHIELD":
            total += 22
        elif label == "HIGH_RISK":
            total += 14
        elif label == "ELEVATED":
            total += 6
    return min(100.0, total)


def _build_summary(evidence: List[Dict[str, Any]], score: float) -> str:
    if not evidence:
        return "PROXIMITY: No strike–civilian correlations in window (no FIRMS anomalies or no nearby OSM facilities)."
    critical = sum(1 for e in evidence if (e.get("riskLabel") or "") == "CRITICAL_PROXIMITY")
    human_shield = sum(1 for e in evidence if (e.get("riskLabel") or "") == "PROBABLE_HUMAN_SHIELD")
    high = sum(1 for e in evidence if (e.get("riskLabel") or "") == "HIGH_RISK")
    parts = [f"{len(evidence)} strike–facility correlation(s)."]
    if critical:
        parts.append(f"{critical} critical proximity.")
    if human_shield:
        parts.append(f"{human_shield} probable human-shield scenario(s).")
    if high:
        parts.append(f"{high} high-risk.")
    return "PROXIMITY: " + " ".join(parts)


def run_proximity_agent(conflict: str) -> Dict[str, Any]:
    """Run PROXIMITY agent: FIRMS strikes + Overpass + optional tunnel sites → evidence + score."""
    region = _conflict_to_region(conflict)
    raw = get_thermal_anomalies.invoke({"region": region, "days": 3})
    anomalies = [
        a for a in (raw if isinstance(raw, list) else [])
        if isinstance(a, dict) and "error" not in a and "lat" in a and "lon" in a
    ]
    events = [
        {
            "lat": float(a["lat"]),
            "lon": float(a["lon"]),
            "source": "FIRMS",
            "description": a.get("type") or "thermal anomaly",
            "acquired": a.get("acquired"),
        }
        for a in anomalies[:MAX_STRIKES]
    ]

    async def _run() -> Dict[str, Any]:
        tunnel_geojson = None
        if region in ("middle_east", "iran"):
            url = (os.getenv("TUNNEL_SITES_GEOJSON_URL") or "").strip()
            if url:
                try:
                    client = get_http_client()
                    tunnel_geojson = await client.get_json(url)
                    if not isinstance(tunnel_geojson, dict) or tunnel_geojson.get("type") != "FeatureCollection":
                        tunnel_geojson = None
                except Exception:
                    tunnel_geojson = None
        evidence = await run_correlation_for_events(events, tunnel_sites_geojson=tunnel_geojson)
        score = _compute_proximity_score(evidence)
        summary = _build_summary(evidence, score)
        return {
            "proximity_score": round(score, 1),
            "evidence": evidence,
            "summary": summary,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        return {
            "proximity_score": 0.0,
            "evidence": [],
            "summary": f"PROXIMITY error: {e}",
        }
