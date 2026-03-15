import json
import os
import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request, Header, Body
from fastapi.responses import Response, JSONResponse, StreamingResponse
from pydantic import BaseModel

from agents.supervisor import analyze_conflict, run_analysis_streaming
from agents.geoint_agent import get_thermal_anomalies, get_conflict_events_for_heatmap, get_theater_events
from agents.iaea_tracker import run_iaea_tracker, fetch_notams
from api.proximity_correlation import run_correlation_for_events
from services.http_client import get_http_client
from services.job_queue import JobQueue, Job
from compliance.sanctions_search import search_sanctions, get_threshold_policy
from compliance.zones import ALL_ZONES, SANCTIONS_ZONES
from compliance.supply_chain import screen_route, get_intermediary_policy
from compliance.risk_score import compute_compliance_risk
from agents.chokepoint_agent import _load_overrides, _save_overrides

router = APIRouter()


class AnalyzeRequest(BaseModel):
    conflict: str


def _get_cache(request: Request):
    return getattr(request.app.state, "analysis_cache", {})


def _get_last_error(request: Request):
    return getattr(request.app.state, "analysis_last_error", {})


# Escalation timeline: keep last N points per conflict for "escalation over the day" UI.
ESCALATION_TIMELINE_MAX_POINTS = int(os.getenv("ESCALATION_TIMELINE_MAX_POINTS", "24"))


def _get_escalation_timeline(request: Request):
    return getattr(request.app.state, "escalation_timeline_history", {})


# Agent keys present in supervisor result (for status recording).
AGENT_KEYS = (
    "finint", "sigint", "news", "geoint", "socmint", "techint", "cyber",
    "energy", "protest", "diplo", "proximity", "narrative", "chokepoint",
)


def push_agent_status(app_state, result: dict) -> None:
    """Record per-agent status from last analysis. Stores rich _meta when present; used by GET /api/agents/status."""
    if not isinstance(result, dict):
        return
    status = getattr(app_state, "agent_status_last", None)
    if status is None:
        return
    for key in AGENT_KEYS:
        agent_result = result.get(key)
        if not isinstance(agent_result, dict):
            status[key] = {"status": "ok"}
            continue
        if agent_result.get("timeout_or_error"):
            meta = agent_result.get("_meta") or {}
            status[key] = {
                "status": "error",
                "fetched_at": meta.get("fetched_at"),
                "duration_ms": meta.get("duration_ms"),
                "confidence": meta.get("confidence"),
                "data_freshness": meta.get("data_freshness"),
                "sources": meta.get("sources", []),
                "fallback_used": meta.get("fallback_used", False),
                "error_summary": meta.get("error_summary"),
            }
            continue
        meta = agent_result.get("_meta") or {}
        status[key] = {
            "status": "ok",
            "fetched_at": meta.get("fetched_at"),
            "duration_ms": meta.get("duration_ms"),
            "confidence": meta.get("confidence"),
            "data_freshness": meta.get("data_freshness"),
            "sources": meta.get("sources", []),
            "fallback_used": meta.get("fallback_used", False),
            "error_summary": meta.get("error_summary"),
        }


ANALYSIS_RUN_HISTORY_MAX = 50


def push_run_history(app_state, conflict: str, at_ts: float, result: dict) -> None:
    """Append one run summary to analysis_run_history for GET /api/agents/history."""
    history = getattr(app_state, "analysis_run_history", None)
    if history is None:
        return
    if not isinstance(result, dict):
        return
    per_agent = {}
    for key in AGENT_KEYS:
        agent_result = result.get(key)
        if isinstance(agent_result, dict):
            meta = agent_result.get("_meta") or {}
            per_agent[key] = {"duration_ms": meta.get("duration_ms"), "status": "error" if agent_result.get("timeout_or_error") else "ok"}
    entry = {
        "at": at_ts,
        "conflict": conflict,
        "escalation_score": result.get("escalation_score"),
        "agents": per_agent,
        "error": result.get("error") or (result.get("_run_error") if isinstance(result.get("_run_error"), str) else None),
    }
    history.append(entry)


def push_escalation_timeline(app_state, conflict: str, at_ts: float, result: dict) -> None:
    """Append one point to escalation timeline history for the conflict. Call after caching analysis."""
    history = getattr(app_state, "escalation_timeline_history", None)
    if history is None:
        return
    score = None
    if isinstance(result, dict):
        score = result.get("escalation_score")
    if score is None:
        return
    try:
        score = float(score)
    except (TypeError, ValueError):
        return
    if conflict not in history:
        history[conflict] = []
    history[conflict].append({"at": at_ts, "escalation_score": round(score, 1)})
    # Keep last N points (e.g. 24 runs ≈ 24h at 1 run/hour, or 6 days at 1 run/6h)
    history[conflict] = history[conflict][-ESCALATION_TIMELINE_MAX_POINTS:]


@router.get("/analyze/stream")
async def analyze_stream(request: Request, conflict: str = "Iran"):
    """
    GET /api/analyze/stream?conflict=Iran
    Server-Sent Events: one event per agent as it completes, then a final supervisor event.
    Event data: {"event": "agent", "agent": "finint", "result": {...}} or {"event": "supervisor", "result": {...}}.
    """
    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_stream():
            try:
                for name, data in run_analysis_streaming(conflict):
                    loop.call_soon_threadsafe(queue.put_nowait, (name, data))
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
            loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.create_task(asyncio.get_running_loop().run_in_executor(None, run_stream))
        while True:
            item = await queue.get()
            if item is None:
                break
            if item[0] == "error":
                yield f"data: {json.dumps({'event': 'error', 'message': item[1]}, default=str)}\n\n"
                break
            name, data = item
            if name == "supervisor":
                yield f"data: {json.dumps({'event': 'supervisor', 'result': data}, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'event': 'agent', 'agent': name, 'result': data}, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/agents/status")
async def agents_status(request: Request):
    """
    GET /api/agents/status
    Per-agent status from last completed analysis. Returns rich object per agent when _meta was present:
    status, fetched_at, duration_ms, confidence, data_freshness, sources, fallback_used, error_summary.
    """
    status = getattr(request.app.state, "agent_status_last", None)
    if status is None:
        return {}
    return dict(status)


@router.get("/agents/health")
async def agents_health():
    """
    GET /api/agents/health
    Per-source health report from HealthRegistry: availability %, avg latency, circuit_open, last_error.
    """
    from agents.health_registry import get_health_registry
    reg = get_health_registry()
    if reg is None:
        return {"sources": [], "summary": {"total_sources": 0, "degraded": 0, "down": 0, "ok": 0}}
    return reg.get_health_report()


@router.get("/agents/history")
async def agents_history(request: Request, limit: int = 20):
    """
    GET /api/agents/history?limit=20
    Last N analysis run summaries: timestamp, conflict, per-agent duration, overall score, errors.
    """
    history = getattr(request.app.state, "analysis_run_history", None)
    if history is None:
        return {"runs": []}
    runs = list(history)[-limit:]
    runs.reverse()
    return {"runs": runs}


@router.get("/analyze/status")
async def analyze_status(request: Request, conflict: str = "Iran"):
    """
    GET /analyze/status?conflict=Iran
    Leichtgewichtige Antwort: ob Cache existiert, wann zuletzt aktualisiert,
    und ob die letzte Background-Analyse fehlgeschlagen ist (error).
    """
    cache = _get_cache(request)
    last_error = _get_last_error(request)
    entry = cache.get(conflict)
    out = {"cached": bool(entry), "conflict": conflict}
    if entry:
        out["at"] = entry.get("at")
    err = last_error.get(conflict)
    if err:
        out["error"] = err
    return out


@router.get("/analyze/latest")
async def get_latest_analysis(request: Request, conflict: str = "Iran"):
    """
    GET /analyze/latest?conflict=Iran
    Liefert die letzte gecachte Analyse (nur vom 10-Min-Auto-Run). Startet keine neue Analyse.
    """
    cache = _get_cache(request)
    entry = cache.get(conflict)
    if not entry:
        return JSONResponse(status_code=404, content={"error": "no_cached_analysis", "conflict": conflict})
    return entry["result"]


@router.get("/analyze/timeline")
async def get_escalation_timeline(request: Request, conflict: str = "Iran"):
    """
    GET /analyze/timeline?conflict=Iran
    Returns escalation score over time for the Escalation Timeline UI.
    Each point is one completed analysis run (at, escalation_score). Points sorted by time ascending.
    """
    history = _get_escalation_timeline(request)
    raw = list(history.get(conflict) or [])
    points = []
    for p in raw:
        at_ts = p.get("at")
        score = p.get("escalation_score")
        try:
            dt = datetime.fromtimestamp(float(at_ts), tz=timezone.utc)
            # label = Uhrzeit (HH:MM), label_with_date = genaue Laufzeit inkl. Datum (DD.MM. HH:MM)
            points.append({
                "at": at_ts,
                "escalation_score": score,
                "datetime_iso": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hour": dt.strftime("%H"),
                "label": dt.strftime("%H:%M"),
                "label_with_date": dt.strftime("%d.%m. %H:%M"),
            })
        except (TypeError, ValueError, OSError):
            points.append({"at": at_ts, "escalation_score": score, "datetime_iso": "", "label": "", "label_with_date": ""})
    points.sort(key=lambda x: x.get("at") or 0)
    return {"conflict": conflict, "points": points}


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


# Max wall-clock time for a single analysis run (e.g. OFAC + 11 agents + LLM).
ANALYZE_TIMEOUT_SEC = 300  # 5 minutes


@router.get("/analyze/refresh")
async def refresh_analysis(request: Request, conflict: str = "Iran", sync: bool = False):
    """
    GET /analyze/refresh?conflict=Iran
    Kicks off a full analysis in the background and returns immediately.
    Add &sync=true to run synchronously and see errors (may timeout on Railway).
    On failure, error is stored and returned via GET /analyze/status.
    """
    app_state = request.app.state
    last_error = _get_last_error(request)
    last_error.pop(conflict, None)  # clear previous error when starting a new run

    if sync:
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            ws_manager = getattr(app_state, "ws_manager", None)
            if ws_manager:
                await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            return {"status": "ok", "conflict": conflict}
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            last_error[conflict] = msg
            return JSONResponse(status_code=504, content={"error": msg, "conflict": conflict})
        except Exception as e:
            import traceback
            last_error[conflict] = str(e)
            return JSONResponse(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})

    async def _run_in_background():
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: analyze_conflict(conflict)),
                timeout=float(ANALYZE_TIMEOUT_SEC),
            )
            at_ts = time.time()
            app_state.analysis_cache[conflict] = {"result": result, "at": at_ts}
            push_escalation_timeline(app_state, conflict, at_ts, result)
            push_agent_status(app_state, result)
            push_run_history(app_state, conflict, at_ts, result)
            last_error.pop(conflict, None)
            ws_manager = getattr(app_state, "ws_manager", None)
            if ws_manager:
                await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
            print(f"[refresh] Analysis for {conflict} done and cached.")
        except asyncio.TimeoutError:
            msg = f"Analysis timed out after {ANALYZE_TIMEOUT_SEC}s."
            last_error[conflict] = msg
            print(f"[refresh] Analysis for {conflict} failed: {msg}")
        except Exception as e:
            last_error[conflict] = str(e)
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
        at_ts = time.time()
        cache[conflict] = {"result": result, "at": at_ts}
        push_escalation_timeline(request.app.state, conflict, at_ts, result)
        push_agent_status(request.app.state, result)
        push_run_history(request.app.state, conflict, at_ts, result)
        ws_manager = getattr(request.app.state, "ws_manager", None)
        if ws_manager:
            await ws_manager.broadcast({**result, "status": "ok", "conflict": conflict})
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
        out = {"evidence": evidence, "region": region, "days": days}
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


# ── Chokepoint manual status overrides ─────────────────────────────────────────

VALID_CHOKEPOINT_STATUSES = {"OPEN", "RESTRICTED", "CONTESTED", "DISRUPTED"}
CHOKEPOINT_NAMES = {"Strait of Hormuz", "Bab el-Mandeb", "Suez Canal"}


@router.get("/chokepoints/overrides")
async def get_chokepoint_overrides():
    """GET /api/chokepoints/overrides – return current manual status overrides."""
    overrides = _load_overrides()
    return overrides


@router.post("/chokepoints/overrides")
async def set_chokepoint_overrides(body: Dict[str, Optional[str]] = Body(default={})):
    """
    POST /api/chokepoints/overrides
    Body: { "Strait of Hormuz": "DISRUPTED", "Bab el-Mandeb": null, ... }
    Merges with existing overrides; null removes override for that chokepoint.
    """
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


# ── IAEA / OE-III Tracker (ADS-B, NOTAMs, IAEA Press – Rafael Grossi) ───────────

@router.get("/iaea-tracker")
async def get_iaea_tracker():
    """
    GET /api/iaea-tracker
    Multisensor-Fusion für IAEO/OE-III (Rafael Grossi):
    - ADS-B: OE-III per Registration + ICAO-Hex (OEIII_ICAO_HEX), Boden-Modus, ORER-Erkennung.
    - NOTAMs: Autorouter.aero (NOTAM_API_URL).
    - METAR ORER: NOAA API (aviationweather.gov/api/data/metar).
    - Flugplan-Status: optional IAEA_FLIGHTPLAN_STATUS_URL.
    - IAEA-Press: RSS, Filter Grossi/DG; Cache TTL (IAEA_CACHE_TTL_MINUTES).
    - Telegram: optional IAEA_TELEGRAM_CHANNELS (Erbil/Kurdistan).
    Antwort: oeiii_adsb, notams, metar_orer, flight_plan_status, iaea_press_grossi,
    iaea_telegram_signals, ground_ops_signals, correlation_notes (hint + confidence), summary.
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
    query: Optional[str] = None
    queries: Optional[List[str]] = None
    include_ownership_chains: bool = False


def _screened_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.post("/compliance/sanctions-check")
async def sanctions_check(body: SanctionsCheckRequest):
    """
    POST /api/compliance/sanctions-check
    Screen one or more names against OFAC SDN (and later EU/UN) sanctions lists.
    Single: body.query. Batch: body.queries (max 5 concurrent). Returns screened_at per result.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    disclaimer = (
        "Intelligence signals only – not legal advice. "
        "Supports due diligence but does not replace legal review."
    )
    try:
        if body.queries:
            # Batch: run up to 5 concurrent
            sem = asyncio.Semaphore(5)

            async def one(q: str) -> Dict[str, Any]:
                async with sem:
                    matches = await search_sanctions(
                        q,
                        include_ownership_chains=body.include_ownership_chains,
                    )
                    return {"query": q, "matches": matches, "screened_at": _screened_at_iso()}

            tasks = [one(q.strip()) for q in body.queries if q and str(q).strip()]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            out = []
            for r in results:
                if isinstance(r, Exception):
                    out.append({"query": "", "matches": [], "screened_at": _screened_at_iso(), "error": str(r)})
                else:
                    out.append(r)
            return {"results": out, "threshold_policy": get_threshold_policy(), "disclaimer": disclaimer}
        q = (body.query or "").strip()
        if not q:
            return JSONResponse(status_code=400, content={"error": "query or queries required"})
        results = await search_sanctions(
            q,
            include_ownership_chains=body.include_ownership_chains,
        )
        return {
            "query": q,
            "matches": results,
            "screened_at": _screened_at_iso(),
            "threshold_policy": get_threshold_policy(),
            "disclaimer": disclaimer,
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


class ComplianceDocumentQAContext(BaseModel):
    """Optional compliance context sent from the frontend (current panel state)."""
    ofac_sample: Optional[List[str]] = None
    ofac_programs_summary: Optional[str] = None
    risk_level: Optional[str] = None
    risk_drivers_summary: Optional[str] = None
    recent_actions_summary: Optional[str] = None


class ComplianceDocumentQARequest(BaseModel):
    """Request for Document QA using compliance context only (no PDF ingest)."""
    question: str
    conflict: Optional[str] = None
    context: Optional[ComplianceDocumentQAContext] = None


def _build_compliance_context(conflict: str, ctx: Optional[ComplianceDocumentQAContext]) -> str:
    """Build a single text block from conflict + context for the LLM."""
    parts = [f"Conflict / region: {conflict or 'Not specified'}."]
    if ctx:
        if ctx.risk_level:
            parts.append(f"Current compliance risk level: {ctx.risk_level}.")
        if ctx.risk_drivers_summary:
            parts.append(f"Risk drivers: {ctx.risk_drivers_summary}")
        if ctx.ofac_sample:
            names = ", ".join(ctx.ofac_sample[:20])
            parts.append(f"OFAC SDN sample entities (from current run): {names}.")
        if ctx.ofac_programs_summary:
            parts.append(f"OFAC programs (name, count): {ctx.ofac_programs_summary}")
        if ctx.recent_actions_summary:
            parts.append(f"Recent OFAC / Treasury actions: {ctx.recent_actions_summary}")
    return "\n".join(parts)


@router.post("/compliance/document-qa")
async def compliance_document_qa(body: ComplianceDocumentQARequest):
    """
    POST /api/compliance/document-qa
    Answer a question using the current compliance context (no PDF/RAG).
    Context: conflict, risk level, risk drivers, OFAC sample, recent actions.
    Uses Haiku; answer is based only on the provided context.
    """
    try:
        from services.haiku_service import document_qa as haiku_document_qa

        if not (body.question or "").strip():
            return JSONResponse(status_code=400, content={"error": "question is required"})

        conflict = (body.conflict or "").strip() or "Iran"
        context_str = _build_compliance_context(conflict, body.context)
        if not context_str.strip():
            context_str = "No compliance context provided."

        result = await haiku_document_qa(
            body.question.strip(),
            [context_str],
            max_chunks=1,
        )
        if not result:
            return {
                "answer": "The service could not process your question at this time.",
                "confidence": 0,
                "sources": [],
                "disclaimer": (
                    "Intelligence signals only – not legal advice. "
                    "Supports due diligence but does not replace legal review."
                ),
            }
        result["disclaimer"] = (
            "Intelligence signals only – not legal advice. "
            "Supports due diligence but does not replace legal review."
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class RouteScreeningWaypoint(BaseModel):
    label: str
    lat: float
    lon: float
    country_code: str = ""
    port_type: str = "port"


class RouteScreeningRequest(BaseModel):
    route_label: str
    waypoints: List[RouteScreeningWaypoint]


@router.post("/compliance/route-screening")
async def route_screening(body: RouteScreeningRequest):
    """
    POST /api/compliance/route-screening
    Screen a trade route against sanctions zones and intermediary policy.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    try:
        wps = [w.model_dump() for w in body.waypoints]
        result = screen_route(body.route_label, wps)
        return {
            **result,
            "disclaimer": (
                "Intelligence signals only – not legal advice. "
                "Supports due diligence but does not replace legal review."
            ),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/compliance/intermediary-policy")
async def get_intermediary_policy_route():
    """
    GET /api/compliance/intermediary-policy
    Returns the active intermediary (middlemen) policy for transparency and audit.
    """
    return {
        "policy": get_intermediary_policy(),
        "note": (
            "This policy defines which transit hubs are flagged for review. "
            "It is configurable and documented; no country is automatically blocked."
        ),
    }


class RiskScoreRequest(BaseModel):
    sanctions_matches: Optional[List[Dict[str, Any]]] = None
    geofencing_alerts: Optional[List[Dict[str, Any]]] = None
    supply_chain_result: Optional[Dict[str, Any]] = None
    ais_anomalies: Optional[List[Dict[str, Any]]] = None
    escalation_level: Optional[str] = None


@router.post("/compliance/risk-score")
async def compliance_risk_score(body: RiskScoreRequest):
    """
    POST /api/compliance/risk-score
    Compute compliance risk score from provided signals.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    try:
        result = compute_compliance_risk(
            sanctions_matches=body.sanctions_matches,
            geofencing_alerts=body.geofencing_alerts,
            supply_chain_result=body.supply_chain_result,
            ais_anomalies=body.ais_anomalies,
            escalation_level=body.escalation_level,
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Document QA (Phase 4) ───────────────────────────────────────────────────


class DocumentIngestRequest(BaseModel):
    url: str
    source: str = "pdf"
    conflict: str = ""


class DocumentQARequest(BaseModel):
    question: str
    source: Optional[str] = None
    conflict: Optional[str] = None
    doc_id: Optional[str] = None


@router.post("/documents/ingest")
async def ingest_document(body: DocumentIngestRequest):
    """
    POST /documents/ingest
    Download and ingest a PDF document for Document QA.
    """
    try:
        from services.pdf_ingest_service import ingest_pdf
        result = await ingest_pdf(
            url=body.url,
            source=body.source,
            conflict=body.conflict,
        )
        if result:
            return result
        return JSONResponse(
            status_code=422,
            content={"error": "Failed to ingest PDF — download or text extraction failed"},
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/documents")
async def list_documents():
    """GET /documents — List all ingested documents."""
    try:
        from services.pdf_ingest_service import list_documents as _list
        return _list()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/documents/qa")
async def document_qa(body: DocumentQARequest):
    """
    POST /documents/qa
    Ask a question over ingested PDF documents.
    Uses semantic search to find relevant chunks, then Haiku (primary)
    or HF extractive QA (fallback) to answer.
    """
    try:
        from services.pdf_ingest_service import find_relevant_chunks, get_chunks

        if body.doc_id:
            chunks = get_chunks(body.doc_id)
            if not chunks:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Document {body.doc_id} not found or has no chunks"},
                )
        else:
            relevant = await find_relevant_chunks(
                body.question,
                source=body.source,
                conflict=body.conflict,
                top_k=5,
            )
            chunks = [r.get("text_preview", "") for r in relevant if r.get("text_preview")]

        if not chunks:
            return {"answer": "No relevant documents found.", "confidence": 0, "sources": []}

        # Try Haiku first
        try:
            from services.haiku_service import document_qa as haiku_qa
            result = await haiku_qa(body.question, chunks, max_chunks=5)
            if result and result.get("answer"):
                return result
        except Exception:
            pass

        # Fallback to HF extractive QA
        try:
            from services.hf_service import document_qa_multi
            hf_results = await document_qa_multi(body.question, chunks, top_k=3)
            if hf_results:
                return {
                    "answer": hf_results[0].get("answer", ""),
                    "confidence": hf_results[0].get("score", 0),
                    "sources": [f"chunk_{r.get('chunk_index', '?')}" for r in hf_results],
                    "all_answers": hf_results,
                }
        except Exception:
            pass

        return {"answer": "Could not process the question.", "confidence": 0, "sources": []}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
