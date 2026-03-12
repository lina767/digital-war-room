import os
import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request, Header
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from agents.supervisor import analyze_conflict
from agents.geoint_agent import get_thermal_anomalies, get_conflict_events_for_heatmap, get_theater_events
from agents.iaea_tracker import run_iaea_tracker, fetch_notams
from api.proximity_correlation import run_correlation_for_events
from services.http_client import get_http_client
from services.job_queue import JobQueue, Job
from compliance.sanctions_search import search_sanctions, get_threshold_policy
from compliance.zones import ALL_ZONES, SANCTIONS_ZONES

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = "Iran"):
    """
    GET /analyze/status?conflict=Iran
    Leichtgewichtige Antwort: ob Cache existiert und wann zuletzt aktualisiert.
    Hilft dem Frontend zu unterscheiden: Backend down vs. noch keine Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return {"cached": False, "conflict": conflict}
    return {"cached": True, "conflict": conflict, "at": entry.get("at")}


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = "Iran"):
    """
    GET /analyze/latest?conflict=Iran
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
                "error": "No cached analysis yet. Analysis runs automatically every 6 hours.",
                "conflict": body.conflict,
            },
        )
    return entry["result"]


@router.get("/analyze/refresh")
async def refresh_analysis(request: Request, conflict: str = "Iran", sync: bool = False):
    """
    GET /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    """
    app_state = request.app.state

    if sync:
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: analyze_conflict(conflict))
            app_state.analysis_cache[conflict] = {"result": result, "at": time.time()}
            return {"status": "ok", "conflict": conflict}
        except Exception as e:
            import traceback
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})

    async def _run_in_background():
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: analyze_conflict(conflict))
            app_state.analysis_cache[conflict] = {"result": result, "at": time.time()}
            print(f"[refresh] Analysis for {conflict} done and cached.")
        except Exception as e:
            print(f"[refresh] Analysis for {conflict} failed: {e}")

    asyncio.create_task(_run_in_background())
    return {"status": "started", "conflict": conflict, "message": "Analysis running in background. Poll /api/analyze/status to check."}


@router.post("/analyze/trigger")
async def trigger_analysis(
    request: Request,
    conflict: str = "Iran",
    x_trigger_secret: str | None = Header(default=None, alias="X-Trigger-Secret"),
):
    """
    Führt einmalig eine Analyse aus und füllt den Cache (z. B. nach Neustart oder Limit-Reset).
    Optional: ANALYZE_TRIGGER_SECRET in Railway setzen, dann Header X-Trigger-Secret mitschicken.
    """
    secret = os.getenv("ANALYZE_TRIGGER_SECRET", "").strip()
    if secret and x_trigger_secret != secret:
        return JSONResponse(status_code=403, content={"error": "Invalid or missing X-Trigger-Secret. Remove ANALYZE_TRIGGER_SECRET from env to disable."})
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
            lambda: get_thermal_anomalies(region=region, days=max(1, min(5, int(days)))),
        )
        anomalies = [
            a for a in (raw if isinstance(raw, list) else [])
            if isinstance(a, dict) and "error" not in a and "lat" in a and "lon" in a
        ]
        return {"strikes": anomalies, "region": region, "days": days}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Max strikes to correlate (Overpass rate limit ~1 req/s; keeps response time reasonable)
_PROXIMITY_ANALYZE_MAX_STRIKES = 15


@router.get("/proximity/analyze")
async def get_proximity_analyze(region: str = "middle_east", days: int = 3):
    """
    GET /api/proximity/analyze?region=...&days=3
    Full proximity analysis server-side: fetches NASA FIRMS strikes, queries Overpass for
    schools/hospitals/government within 300m, optionally checks tunnel/military sites for
    PROBABLE_HUMAN_SHIELD. Returns { evidence: [...] } (camelCase for frontend).
    Replaces client-side Overpass loop; use this for the Dashboard "Run" button.
    """
    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: get_thermal_anomalies(region=region, days=max(1, min(5, int(days)))),
        )
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
            for a in anomalies[: _PROXIMITY_ANALYZE_MAX_STRIKES]
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
        return {"evidence": evidence, "region": region, "days": days}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── IAEA / OE-III Tracker (ADS-B, NOTAMs, IAEA Press – Rafael Grossi) ───────────

@router.get("/iaea-tracker")
async def get_iaea_tracker():
    """
    GET /api/iaea-tracker
    Trackt die IAEO bzw. das Flugzeug von Rafael Grossi (OE-III):
    - ADS-B: Filter auf OE-III (opendata.adsb.fi / api.adsb.lol).
    - NOTAMs: Autorouter.aero (NOTAM_API_URL), itemas=[EDDS,LOWW,OIIE].
    - IAEA-Pressemitteilungen: Erwähnungen Grossi/Director General; Korrelation mit Flugdaten.
    """
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_iaea_tracker)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/notam")
async def get_notam(
    locations: str = "EDDS,LOWW,OIIE",
    limit: int = 10,
    offset: int = 0,
):
    """
    GET /api/notam?locations=EDDS,LOWW,OIIE&limit=10&offset=0
    NOTAMs für ICAO-Plätze (Autorouter.aero: itemas=["EDDS",...], offset, limit).
    """
    icao_list = [s.strip().upper() for s in locations.split(",") if s.strip()][:20]
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: fetch_notams(icao_locations=icao_list or None, limit=limit, offset=offset),
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Conflict events for heatmap (ACLED lat/lon + intensity) ────────────────────

@router.get("/conflict-events")
async def get_conflict_events(conflict: str = "Iran", limit: int = 200):
    """
    GET /api/conflict-events?conflict=Iran&limit=200
    Returns conflict events with lat, lon, intensity for heatmap layer (ACLED).
    Requires ACLED_EMAIL + ACLED_PASSWORD (OAuth) or legacy ACLED_API_KEY. Intensity derived from fatalities and event type.
    """
    try:
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            lambda: get_conflict_events_for_heatmap(conflict, limit=max(50, min(500, limit))),
        )
        return {"events": events, "conflict": conflict}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/theater-events")
async def get_theater_events_route(conflict: str = "Iran", limit: int = 400):
    """
    GET /api/theater-events?conflict=Iran&limit=400
    Returns unified theater map events: FIRMS thermal anomalies + ACLED + UCDP (with lat/lon).
    Each event has lat, lon, event_type (airstrike | missile | drone | explosion | naval | fire | other), source, confidence, label.
    Use for Theater Map layer (e.g. Iran) with type-specific icons.
    """
    try:
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            lambda: get_theater_events(conflict, limit=max(100, min(600, limit))),
        )
        return {"events": events, "conflict": conflict}
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
        client = get_http_client()
        data = await client.get_json(url)
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
async def webhook_proximity_events(request: Request, body: ProximityWebhookBody):
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
            client = get_http_client()
            tunnel_geojson = await client.get_json(body.tunnel_sites_geojson_url, timeout=10.0)
        except Exception:
            tunnel_geojson = None

    queue: JobQueue | None = getattr(request.app.state, "job_queue", None)

    async def _handle_proximity_job(payload: Dict[str, Any]) -> Dict[str, Any]:
        evts = payload.get("events") or []
        geojson = payload.get("tunnel_geojson")
        evidence = await run_correlation_for_events(evts, tunnel_sites_geojson=geojson)
        return {"evidence": evidence, "count": len(evidence)}

    # Fallback: falls JobQueue nicht verfügbar ist, weiterhin synchron ausführen (Backwards-Compatibility)
    if queue is None:
        try:
            result = await _handle_proximity_job({"events": events, "tunnel_geojson": tunnel_geojson})
            return result
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    job = await queue.enqueue(
        "proximity_correlation",
        {"events": events, "tunnel_geojson": tunnel_geojson},
        handler=_handle_proximity_job,
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/webhooks/proximity-events/{job_id}")
async def get_proximity_job_status(request: Request, job_id: str):
    """
    GET /api/webhooks/proximity-events/{job_id}
    Returns status and (when finished) result for a previously enqueued proximity correlation job.
    """
    queue: JobQueue | None = getattr(request.app.state, "job_queue", None)
    if queue is None:
        return JSONResponse(status_code=503, content={"error": "Job queue not available"})
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


# ── Sanctions Compliance ─────────────────────────────────────────────────────

class SanctionsCheckRequest(BaseModel):
    query: str
    include_ownership_chains: bool = False


@router.post("/compliance/sanctions-check")
async def sanctions_check(body: SanctionsCheckRequest):
    """
    POST /api/compliance/sanctions-check
    Screen a firm/partner name against OFAC SDN (and later EU/UN) sanctions lists.
    Returns matches with match_level (EXACT/STRONG_FUZZY/WEAK_FUZZY/REVIEW), score, source.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    try:
        results = await search_sanctions(
            body.query,
            include_ownership_chains=body.include_ownership_chains,
        )
        return {
            "query": body.query,
            "matches": results,
            "threshold_policy": get_threshold_policy(),
            "disclaimer": (
                "Intelligence signals only – not legal advice. "
                "Supports due diligence but does not replace legal review."
            ),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/compliance/zones")
async def get_compliance_zones():
    """
    GET /api/compliance/zones
    Returns all configured sanctions and conflict zones (bounding boxes).
    """
    return {
        "sanctions_zones": [z.to_dict() for z in SANCTIONS_ZONES],
        "all_zones": [z.to_dict() for z in ALL_ZONES],
    }


@router.get("/compliance/threshold-policy")
async def get_compliance_threshold_policy():
    """
    GET /api/compliance/threshold-policy
    Returns the current fuzzy matching threshold policy for transparency.
    """
    return get_threshold_policy()
