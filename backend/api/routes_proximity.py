"""
Proximity analyzer, chokepoint overrides, tunnel sites, and proximity webhook routes.
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from api.deps import JobQueueDep
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from agents.chokepoint_agent import _load_overrides, _save_overrides
from agents.geoint_agent import get_thermal_anomalies
from api.proximity_correlation import run_correlation_for_events
from services.http_client import get_http_client
from services.job_queue import Job, JobQueue

router = APIRouter()

# Max strikes to correlate (Overpass: batched union queries + TTL cache in services.proximity_correlation)
_PROXIMITY_ANALYZE_MAX_STRIKES = 15

VALID_CHOKEPOINT_STATUSES = {"OPEN", "RESTRICTED", "CONTESTED", "DISRUPTED"}
CHOKEPOINT_NAMES = {"Strait of Hormuz", "Bab el-Mandeb", "Suez Canal"}


@router.get("/proximity/strikes")
async def get_proximity_strikes(region: str = "middle_east", days: int = 3):
    """
    GET /api/proximity/strikes?region=...&days=3
    Returns NASA FIRMS VIIRS_SNPP_NRT thermal anomalies for the region (strike triggers).
    Used by the frontend Proximity Analyzer to correlate with civilian infrastructure (Overpass).
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: get_thermal_anomalies(region=region, days=max(1, min(5, int(days)))),
        )
        anomalies = [
            a
            for a in (raw if isinstance(raw, list) else [])
            if isinstance(a, dict) and "error" not in a and "lat" in a and "lon" in a
        ]
        return {"strikes": anomalies, "region": region, "days": days}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/proximity/analyze")
async def get_proximity_analyze(region: str = "middle_east", days: int = 3):
    """
    GET /api/proximity/analyze?region=...&days=3
    Full proximity analysis server-side: fetches NASA FIRMS strikes, batched Overpass queries for
    schools/hospitals/government within 300m (with TTL cache), optionally checks tunnel/military sites for
    PROBABLE_HUMAN_SHIELD. Returns { evidence: [...] } (camelCase for frontend).
    Replaces client-side Overpass loop; use this for the Dashboard "Run" button.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: get_thermal_anomalies(region=region, days=max(1, min(5, int(days)))),
        )
        anomalies = [
            a
            for a in (raw if isinstance(raw, list) else [])
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
            for a in anomalies[:_PROXIMITY_ANALYZE_MAX_STRIKES]
        ]
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
        out = {"evidence": evidence, "region": region, "days": days}
        if evidence:
            out["advanced_metrics"] = {
                "semantic_enriched": sum(1 for e in evidence if e.get("semanticEventType")),
                "vision_enriched": sum(1 for e in evidence if e.get("visionVerification")),
                "dynamic_labels": sum(1 for e in evidence if e.get("riskLabelDynamic")),
            }
        if len(evidence) == 0:
            if len(events) == 0:
                out["reason_empty"] = "no_strikes"
                if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], dict) and raw[0].get("error"):
                    out["error_message"] = str(raw[0].get("error", ""))
            else:
                out["reason_empty"] = "no_facilities_near_strikes"
        return out
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/chokepoints/overrides")
async def get_chokepoint_overrides():
    """GET /api/chokepoints/overrides – return current manual status overrides."""
    overrides = _load_overrides()
    return overrides


@router.post("/chokepoints/overrides")
async def set_chokepoint_overrides(body: Optional[Dict[str, Optional[str]]] = None):
    """
    POST /api/chokepoints/overrides
    Body: { "Strait of Hormuz": "DISRUPTED", "Bab el-Mandeb": null, ... }
    Merges with existing overrides; null removes override for that chokepoint.
    """
    if body is None:
        body = {}
    current = _load_overrides()
    for cp_name, value in body.items():
        if cp_name not in CHOKEPOINT_NAMES:
            continue
        if value is None or (isinstance(value, str) and value.strip() == ""):
            current.pop(cp_name, None)
        elif isinstance(value, str) and value.strip().upper() in VALID_CHOKEPOINT_STATUSES:
            current[cp_name] = value.strip().upper()
    _save_overrides(current)
    return current


@router.get("/proximity/tunnel-sites")
async def get_tunnel_sites():
    """
    GET /api/proximity/tunnel-sites
    Returns a GeoJSON FeatureCollection of suspected IRGC tunnel / military sites.
    Set TUNNEL_SITES_GEOJSON_URL in env to a URL that serves the GeoJSON; otherwise returns empty.
    Frontend and webhook use this to flag PROBABLE_HUMAN_SHIELD when a site is within 100m of a school/hospital.
    """
    url = (os.getenv("TUNNEL_SITES_GEOJSON_URL") or "").strip()
    if not url:
        return {"type": "FeatureCollection", "features": []}
    try:
        client = get_http_client()
        data = await client.get_json(url)
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            return data
        return {"type": "FeatureCollection", "features": []}
    except Exception:
        return {"type": "FeatureCollection", "features": []}


class ProximityEventItem(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    source: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = Field(None, max_length=4000)


class ProximityWebhookBody(BaseModel):
    events: List[ProximityEventItem] = Field(..., min_length=1, max_length=500)
    tunnel_sites_geojson_url: Optional[str] = Field(None, max_length=2048)
    tunnel_sites: Optional[Dict[str, Any]] = None  # inline GeoJSON FeatureCollection

    @field_validator("tunnel_sites_geojson_url", mode="before")
    @classmethod
    def _strip_tunnel_url(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise TypeError("tunnel_sites_geojson_url must be a string")
        s = v.strip()
        return s if s else None

    @field_validator("tunnel_sites_geojson_url")
    @classmethod
    def _tunnel_url_scheme(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("tunnel_sites_geojson_url must start with http:// or https://")
        return v


@router.post("/webhooks/proximity-events")
async def webhook_proximity_events(body: ProximityWebhookBody, queue: JobQueueDep):
    """
    POST /api/webhooks/proximity-events
    Accepts a list of events (lat, lon, optional source/description). Batched Overpass correlation
    for schools/hospitals/government within 300m, correlates distance, and optionally checks
    tunnel_sites (or tunnel_sites_geojson_url) for PROBABLE_HUMAN_SHIELD within 100m of the same facility.
    Returns { "evidence": [ ... ] }.
    Use case: cron job that fetches Liveuamap (or other) events and POSTs here; or external system webhook.
    """
    events = [{"lat": e.lat, "lon": e.lon, "source": e.source, "description": e.description} for e in body.events]
    tunnel_geojson = body.tunnel_sites
    if not tunnel_geojson and body.tunnel_sites_geojson_url:
        try:
            client = get_http_client()
            tunnel_geojson = await client.get_json(body.tunnel_sites_geojson_url, timeout=10.0)
        except Exception:
            tunnel_geojson = None

    async def _handle_proximity_job(payload: Dict[str, Any]) -> Dict[str, Any]:
        evts = payload.get("events") or []
        geojson = payload.get("tunnel_geojson")
        evidence = await run_correlation_for_events(evts, tunnel_sites_geojson=geojson)
        return {"evidence": evidence, "count": len(evidence)}

    job = await queue.enqueue(
        "proximity_correlation",
        {"events": events, "tunnel_geojson": tunnel_geojson},
        handler=_handle_proximity_job,
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/webhooks/proximity-events/{job_id}")
async def get_proximity_job_status(job_id: str, queue: JobQueueDep):
    """
    GET /api/webhooks/proximity-events/{job_id}
    Returns status and (when finished) result for a previously enqueued proximity correlation job.
    """
    job: Job | None = await queue.get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
