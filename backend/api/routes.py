import os
import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request, Header
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from agents.supervisor import analyze_conflict
from agents.geoint_agent import get_thermal_anomalies
from api.proximity_correlation import run_correlation_for_events

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = "US-Iran"):
    """
    GET /analyze/status?conflict=US-Iran
    Leichtgewichtige Antwort: ob Cache existiert und wann zuletzt aktualisiert.
    Hilft dem Frontend zu unterscheiden: Backend down vs. noch keine Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return {"cached": False, "conflict": conflict}
    return {"cached": True, "conflict": conflict, "at": entry.get("at")}


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = "US-Iran"):
    """
    GET /analyze/latest?conflict=US-Iran
    Liefert die letzte gecachte Analyse (nur vom 10-Min-Auto-Run). Startet keine neue Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return Response(status_code=404)
    return entry["result"]


@router.post("/analyze")
async def analyze(request: Request, body: AnalyzeRequest):
    """
    POST /analyze – startet KEINE neue Analyse.
    Gibt nur die gecachte Analyse zurück (wie GET /analyze/latest).
    Analysen laufen stündlich im Hintergrund.
    """
    cache = _get_cache(request)
    entry = cache.get(body.conflict)
    if not entry:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No cached analysis yet. Analysis runs automatically every hour.",
                "conflict": body.conflict,
            },
        )
    return entry["result"]


@router.post("/analyze/trigger")
async def trigger_analysis(
    request: Request,
    conflict: str = "US-Iran",
    x_trigger_secret: str | None = Header(default=None, alias="X-Trigger-Secret"),
):
    """
    Führt einmalig eine Analyse aus und füllt den Cache (z. B. nach Neustart oder Limit-Reset).
    Optional: ANALYZE_TRIGGER_SECRET in Railway setzen, dann Header X-Trigger-Secret mitschicken.
    """
    secret = os.getenv("ANALYZE_TRIGGER_SECRET", "").strip()
    if secret and x_trigger_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Trigger-Secret"})
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: analyze_conflict(conflict))
        cache = _get_cache(request)
        cache[conflict] = {"result": result, "at": time.time()}
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Proximity Analyzer: strike data (NASA FIRMS thermal anomalies) ───────────

@router.get("/proximity/strikes")
async def get_proximity_strikes(region: str = "middle_east", days: int = 3):
    """
    GET /api/proximity/strikes?region=...&days=3
    Returns NASA FIRMS VIIRS_SNPP_NRT thermal anomalies for the region (strike triggers).
    Used by the frontend Proximity Analyzer to correlate with civilian infrastructure (Overpass).
    """
    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: get_thermal_anomalies.invoke({"region": region, "days": max(1, min(5, int(days)))}),
        )
        anomalies = [
            a for a in (raw if isinstance(raw, list) else [])
            if isinstance(a, dict) and "error" not in a and "lat" in a and "lon" in a
        ]
        return {"strikes": anomalies, "region": region, "days": days}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Proximity: IRGC tunnel / military sites GeoJSON (for human-shield correlation) ─

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
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            return data
        return {"type": "FeatureCollection", "features": []}
    except Exception:
        return {"type": "FeatureCollection", "features": []}


# ── Webhook: incoming events (e.g. from Liveuamap, cron, or external aggregator) ─

class ProximityEventItem(BaseModel):
    lat: float
    lon: float
    source: Optional[str] = None
    description: Optional[str] = None


class ProximityWebhookBody(BaseModel):
    events: List[ProximityEventItem]
    tunnel_sites_geojson_url: Optional[str] = None
    tunnel_sites: Optional[Dict[str, Any]] = None  # inline GeoJSON FeatureCollection


@router.post("/webhooks/proximity-events")
async def webhook_proximity_events(body: ProximityWebhookBody):
    """
    POST /api/webhooks/proximity-events
    Accepts a list of events (lat, lon, optional source/description). For each event, queries Overpass
    for schools/hospitals/government within 300m, correlates distance, and optionally checks
    tunnel_sites (or tunnel_sites_geojson_url) for PROBABLE_HUMAN_SHIELD within 100m of the same facility.
    Returns { "evidence": [ ... ] }.
    Use case: cron job that fetches Liveuamap (or other) events and POSTs here; or external system webhook.
    """
    events = [{"lat": e.lat, "lon": e.lon, "source": e.source, "description": e.description} for e in body.events]
    tunnel_geojson = body.tunnel_sites
    if not tunnel_geojson and body.tunnel_sites_geojson_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(body.tunnel_sites_geojson_url)
                r.raise_for_status()
                tunnel_geojson = r.json()
        except Exception:
            tunnel_geojson = None
    try:
        evidence = await run_correlation_for_events(events, tunnel_sites_geojson=tunnel_geojson)
        return {"evidence": evidence, "count": len(evidence)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
