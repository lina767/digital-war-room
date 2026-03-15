"""
PROXIMITY Agent – Strike–civilian infrastructure correlation (human-shield / collateral risk).
Uses NASA FIRMS thermal anomalies as strike triggers, Overpass (OSM) for schools/hospitals/government,
optional tunnel/military sites GeoJSON for PROBABLE_HUMAN_SHIELD. Runs in the same pipeline as
other agents; also available via GET /api/proximity/analyze and the Dashboard "Run" button.
"""
import asyncio
import os
from typing import Any, Dict, List, Optional

from .utils import run_async
from agents.geoint_agent import get_thermal_anomalies, get_conflict_region
from services.proximity_correlation import run_correlation_for_events
from services.http_client import get_http_client

# Max strike events to correlate (Overpass rate limit; keep agent run time bounded)
MAX_STRIKES = 15

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


async def _generate_haiku_summary_proximity(
    conflict: str,
    evidence: List[Dict[str, Any]],
    score: float,
) -> Optional[str]:
    """Optional 2-3 sentence strike-civilian impact narrative via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary
        import json
        compact = {
            "conflict": conflict,
            "proximity_score": score,
            "evidence_count": len(evidence),
            "critical": sum(1 for e in evidence if (e.get("riskLabel") or "") == "CRITICAL_PROXIMITY"),
            "human_shield": sum(1 for e in evidence if (e.get("riskLabel") or "") == "PROBABLE_HUMAN_SHIELD"),
            "high_risk": sum(1 for e in evidence if (e.get("riskLabel") or "") == "HIGH_RISK"),
            "sample": [
                {"riskLabel": e.get("riskLabel"), "facility_type": e.get("facility_type"), "distance_m": e.get("distance_m")}
                for e in (evidence or [])[:5]
            ],
        }
        data = json.dumps(compact, indent=2)
        system = (
            "You are a conflict analyst. Summarize the following strike–civilian proximity data "
            "in 2-3 sentences: thermal anomalies correlated with schools/hospitals, human-shield or "
            "collateral risk. Be concise. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256)
        return out.strip() if out else None
    except Exception:
        return None


def run_proximity_agent(conflict: str) -> Dict[str, Any]:
    """Run PROXIMITY agent: FIRMS strikes + Overpass + optional tunnel sites → evidence + score."""
    region = get_conflict_region(conflict)
    raw = get_thermal_anomalies(region=region, days=3)
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

    error_message = None
    reason_empty = None
    if len(events) == 0:
        reason_empty = "no_strikes"
        if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], dict) and raw[0].get("error"):
            error_message = str(raw[0].get("error", ""))

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
        current_reason = reason_empty
        if len(evidence) == 0 and len(events) > 0:
            current_reason = "no_facilities_near_strikes"
        score = _compute_proximity_score(evidence)
        rule_summary = _build_summary(evidence, score)
        llm_summary = await _generate_haiku_summary_proximity(conflict, evidence, score)
        summary = llm_summary if llm_summary else rule_summary
        out = {
            "proximity_score": round(score, 1),
            "evidence": evidence,
            "summary": summary,
        }
        if current_reason is not None:
            out["reason_empty"] = current_reason
        if error_message is not None:
            out["error_message"] = error_message
        return out

    try:
        result = run_async(_run())
        if reason_empty is not None and "reason_empty" not in result:
            result["reason_empty"] = reason_empty
        if error_message is not None and "error_message" not in result:
            result["error_message"] = error_message
        return result
    except Exception as e:
        return {
            "proximity_score": 0.0,
            "evidence": [],
            "summary": f"PROXIMITY error: {e}",
            "reason_empty": "error",
            "error_message": str(e),
        }
