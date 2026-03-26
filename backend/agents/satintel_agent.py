"""
SATINTEL Agent.
Satellite imagery analysis using Sentinel Hub Process API and Copernicus Data Space catalogue.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from services.http_client import get_http_client
from services.sentinelhub_auth import get_sentinelhub_token_async, has_sentinelhub_credentials

from .utils import SourceResult, build_agent_meta, run_async, safe_float, utc_now_iso

if TYPE_CHECKING:
    from .context import AgentContext

logger = logging.getLogger(__name__)

SENTINELHUB_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"
COPERNICUS_ODATA_PRODUCTS_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

REGION_BBOX = {
    "middle_east": [35.0, 20.0, 65.0, 40.0],  # west, south, east, north
    "eastern_europe": [22.0, 44.0, 40.0, 55.0],
    "east_asia": [100.0, 20.0, 130.0, 45.0],
    "africa": [20.0, -5.0, 45.0, 25.0],
    "lebanon": [35.05, 33.05, 36.65, 34.68],
    "gaza_israel": [34.0, 29.0, 36.0, 34.0],
    "iran": [44.0, 24.0, 64.0, 40.0],
    "yemen": [42.0, 12.0, 56.0, 20.0],
}


def _region_from_conflict(conflict: str) -> str:
    cl = (conflict or "").lower()
    if any(k in cl for k in ["lebanon", "hezbollah"]):
        return "lebanon"
    if any(k in cl for k in ["iran", "israel", "gaza", "yemen", "syria", "iraq"]):
        return "middle_east"
    if any(k in cl for k in ["ukraine", "russia", "donbas", "belarus"]):
        return "eastern_europe"
    if any(k in cl for k in ["taiwan", "china", "korea", "myanmar"]):
        return "east_asia"
    if any(k in cl for k in ["sudan", "ethiopia", "drc", "sahel", "mali"]):
        return "africa"
    return "middle_east"


def _bbox_from_context(context: Optional["AgentContext"]) -> Optional[List[float]]:
    if not context or not getattr(context, "focus_regions", None):
        return None
    points = [r for r in (context.focus_regions or []) if isinstance(r, dict) and r.get("lat") and r.get("lon")]
    if not points:
        return None
    lats = [float(p["lat"]) for p in points[:20]]
    lons = [float(p["lon"]) for p in points[:20]]
    pad = 1.2
    return [min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad]


def _sentinelhub_request_payload(bbox: List[float], time_from_iso: str, time_to_iso: str, width: int = 96) -> Dict[str, Any]:
    return {
        "input": {
            "bounds": {"bbox": bbox},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": time_from_iso, "to": time_to_iso}}}],
        },
        "output": {
            "width": width,
            "height": width,
            "responses": [{"identifier": "default", "format": {"type": "application/json"}}],
        },
        "evalscript": """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "B12", "dataMask"],
    output: { bands: 3, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) { return [0, 0, 0]; }
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-6);
  let nbr = (sample.B08 - sample.B12) / (sample.B08 + sample.B12 + 1e-6);
  let thermalProxy = sample.B12;
  return [ndvi, nbr, thermalProxy];
}
""".strip(),
    }


def _stats_delta(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, float]:
    return {
        "ndvi_delta": round((after.get("ndvi_mean", 0.0) - before.get("ndvi_mean", 0.0)), 4),
        "nbr_delta": round((after.get("nbr_mean", 0.0) - before.get("nbr_mean", 0.0)), 4),
        "thermal_delta": round(
            (after.get("thermal_proxy_mean", 0.0) - before.get("thermal_proxy_mean", 0.0)),
            4,
        ),
    }


def _change_detection_signals(delta: Dict[str, float]) -> List[str]:
    """Heuristic labels from baseline vs recent window (Sentinel-2 L2A composite stats)."""
    out: List[str] = []
    d_ndvi = delta.get("ndvi_delta", 0.0)
    d_nbr = delta.get("nbr_delta", 0.0)
    d_th = delta.get("thermal_delta", 0.0)
    if abs(d_ndvi) >= 0.07:
        out.append(
            f"NDVI change {d_ndvi:+.2f} (baseline vs recent) — possible vegetation / land-cover or infrastructure shift in AOI."
        )
    if abs(d_nbr) >= 0.05:
        out.append(
            f"NBR change {d_nbr:+.2f} — possible burn scar, bare soil, or built-up change between windows."
        )
    if abs(d_th) >= 0.03:
        out.append(f"SWIR proxy change {d_th:+.2f} — thermal / moisture signal differed between periods.")
    return out


def _extract_raster_stats(resp_json: Dict[str, Any]) -> Dict[str, float]:
    data = resp_json.get("data")
    if not isinstance(data, list):
        return {"ndvi_mean": 0.0, "nbr_mean": 0.0, "thermal_proxy_mean": 0.0}
    ndvi_vals: List[float] = []
    nbr_vals: List[float] = []
    th_vals: List[float] = []
    for px in data:
        if not isinstance(px, list) or len(px) < 3:
            continue
        ndvi_vals.append(safe_float(px[0]) or 0.0)
        nbr_vals.append(safe_float(px[1]) or 0.0)
        th_vals.append(safe_float(px[2]) or 0.0)
    if not ndvi_vals:
        return {"ndvi_mean": 0.0, "nbr_mean": 0.0, "thermal_proxy_mean": 0.0}
    n = float(len(ndvi_vals))
    return {
        "ndvi_mean": round(sum(ndvi_vals) / n, 4),
        "nbr_mean": round(sum(nbr_vals) / n, 4),
        "thermal_proxy_mean": round(sum(th_vals) / n, 4),
    }


async def _query_copernicus_products_count(bbox: List[float], from_iso: str) -> int:
    west, south, east, north = bbox
    footprint = (
        "geography'SRID=4326;POLYGON(("
        f"{west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}"
        "))'"
    )
    filter_q = (
        f"Collection/Name eq 'SENTINEL-2' and ContentDate/Start gt {from_iso} and "
        f"OData.CSC.Intersects(area={footprint})"
    )
    url = f"{COPERNICUS_ODATA_PRODUCTS_URL}/$count"
    client = get_http_client()
    resp = await client.request("GET", url, params={"$filter": filter_q}, retries=1)
    try:
        return max(0, int((resp.text or "0").strip()))
    except ValueError:
        return 0


def _compute_satintel_score(
    stats: Dict[str, float], product_count: int, change_bonus: float = 0.0
) -> Tuple[float, List[str]]:
    ndvi = stats.get("ndvi_mean", 0.0)
    nbr = stats.get("nbr_mean", 0.0)
    thermal = stats.get("thermal_proxy_mean", 0.0)
    findings: List[str] = []

    score = 20.0
    if nbr < 0.15:
        score += 25
        findings.append("Low NBR signal (possible burn/scar zones).")
    if thermal > 0.10:
        score += 20
        findings.append("Elevated SWIR thermal proxy detected.")
    if ndvi < 0.10:
        score += 10
        findings.append("Low vegetation signal in AOI.")
    score += min(25.0, product_count / 2.0)
    if product_count > 0:
        findings.append(f"Copernicus catalogue returned {product_count} Sentinel-2 products in lookback window.")
    if change_bonus > 0:
        score += change_bonus

    return round(max(0.0, min(100.0, score)), 1), findings


def _fallback_result(conflict: str, reason: str) -> Dict[str, Any]:
    from .health_registry import get_health_registry

    fetched_at = utc_now_iso()
    src = [
        SourceResult(name="Sentinel Hub Process API", status="error", fetched_at=fetched_at, record_count=0),
        SourceResult(name="Copernicus Data Space OData", status="error", fetched_at=fetched_at, record_count=0),
    ]
    reg = get_health_registry()
    if reg:
        for sr in src:
            reg.record_result(sr.name, "satintel", sr)
    return {
        "conflict": conflict,
        "satintel_score": 15.0,
        "imagery_signals": [],
        "aoi": {},
        "copernicus_products": [],
        "source_status": {"sentinelhub": "error", "copernicus": "error"},
        "summary": "SATINTEL degraded mode: no satellite API data available.",
        "_meta": build_agent_meta(
            "satintel",
            fetched_at,
            0,
            src,
            fallback_used=True,
            error_summary=reason,
            has_any_data=False,
        ),
    }


def run_satintel_agent(
    conflict: str, context: Optional["AgentContext"] = None, peers: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()

    if not has_sentinelhub_credentials():
        return _fallback_result(conflict, "Missing SENTINELHUB_CLIENT_ID/SENTINELHUB_CLIENT_SECRET")

    region = _region_from_conflict(conflict)
    bbox = _bbox_from_context(context) or REGION_BBOX.get(region, REGION_BBOX["middle_east"])

    end_dt = datetime.now(timezone.utc)
    recent_start = end_dt - timedelta(days=10)
    recent_from_iso = recent_start.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    recent_to_iso = end_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Older window for before/after change detection (~11–22 days ago vs recent 10 days; one day gap reduces overlap).
    baseline_end = end_dt - timedelta(days=11)
    baseline_start = end_dt - timedelta(days=22)
    baseline_from_iso = baseline_start.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    baseline_to_iso = baseline_end.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    from_odata = recent_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    async def _run() -> Dict[str, Any]:
        token = await get_sentinelhub_token_async()
        if not token:
            return _fallback_result(conflict, "Sentinel Hub token unavailable")

        headers = {"Authorization": f"Bearer {token}"}
        payload_recent = _sentinelhub_request_payload(
            bbox=bbox, time_from_iso=recent_from_iso, time_to_iso=recent_to_iso
        )
        payload_baseline = _sentinelhub_request_payload(
            bbox=bbox, time_from_iso=baseline_from_iso, time_to_iso=baseline_to_iso
        )

        source_results: List[SourceResult] = []
        status = {"sentinelhub": "error", "copernicus": "error"}
        imagery_signals: List[Dict[str, Any]] = []
        product_count = 0
        stats: Dict[str, float] = {"ndvi_mean": 0.0, "nbr_mean": 0.0, "thermal_proxy_mean": 0.0}
        stats_baseline: Dict[str, float] = {"ndvi_mean": 0.0, "nbr_mean": 0.0, "thermal_proxy_mean": 0.0}
        sh_requests_ok = 0
        error_summary: Optional[str] = None

        try:
            client = get_http_client()
            resp_recent = await client.request(
                "POST", SENTINELHUB_PROCESS_URL, json=payload_recent, headers=headers, retries=1
            )
            stats = _extract_raster_stats(resp_recent.json())
            sh_requests_ok += 1
            try:
                resp_base = await client.request(
                    "POST", SENTINELHUB_PROCESS_URL, json=payload_baseline, headers=headers, retries=1
                )
                stats_baseline = _extract_raster_stats(resp_base.json())
                sh_requests_ok += 1
            except Exception as e2:
                logger.info("SATINTEL baseline Process API failed (recent still ok): %s", e2)
            status["sentinelhub"] = "ok"
            source_results.append(
                SourceResult(
                    name="Sentinel Hub Process API",
                    status="ok",
                    fetched_at=fetched_at,
                    record_count=sh_requests_ok,
                )
            )
        except Exception as e:
            error_summary = f"sentinelhub_process_failed:{type(e).__name__}"
            source_results.append(
                SourceResult(name="Sentinel Hub Process API", status="error", fetched_at=fetched_at, record_count=0)
            )

        try:
            product_count = await _query_copernicus_products_count(bbox, from_odata)
            status["copernicus"] = "ok"
            source_results.append(
                SourceResult(name="Copernicus Data Space OData", status="ok", fetched_at=fetched_at, record_count=product_count)
            )
        except Exception as e:
            if error_summary:
                error_summary = f"{error_summary};copernicus_count_failed:{type(e).__name__}"
            else:
                error_summary = f"copernicus_count_failed:{type(e).__name__}"
            source_results.append(
                SourceResult(name="Copernicus Data Space OData", status="error", fetched_at=fetched_at, record_count=0)
            )

        delta = _stats_delta(stats_baseline, stats)
        change_msgs = _change_detection_signals(delta) if sh_requests_ok >= 2 else []
        change_bonus = min(18.0, len(change_msgs) * 6.0)
        score, findings = _compute_satintel_score(stats, product_count, change_bonus=change_bonus)
        for f in findings:
            imagery_signals.append({"signal": f, "confidence": "nominal"})
        for f in change_msgs:
            imagery_signals.append({"signal": f, "confidence": "change_detection"})

        duration_ms = int((time.perf_counter() - start) * 1000)
        has_data = status["sentinelhub"] == "ok" or status["copernicus"] == "ok"
        from .health_registry import get_health_registry

        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "satintel", sr)
        change_detection: Dict[str, Any] = {
            "baseline": {
                "from": baseline_from_iso,
                "to": baseline_to_iso,
                "stats": stats_baseline,
            },
            "recent": {
                "from": recent_from_iso,
                "to": recent_to_iso,
                "stats": stats,
            },
            "delta": delta,
            "windows_ok": sh_requests_ok >= 2,
        }
        return {
            "conflict": conflict,
            "satintel_score": score,
            "imagery_signals": imagery_signals,
            "change_detection": change_detection,
            "aoi": {
                "region": region,
                "bbox": {"west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3]},
                "time_range": {"from": recent_from_iso, "to": recent_to_iso},
                "stats": stats,
            },
            "copernicus_products": [{"dataset": "SENTINEL-2", "lookback_days": 10, "count": product_count}],
            "source_status": status,
            "summary": (
                f"SATINTEL: Sentinel-2 recent window NDVI {stats.get('ndvi_mean', 0):.2f}, NBR {stats.get('nbr_mean', 0):.2f}, "
                f"ΔNDVI {delta.get('ndvi_delta', 0):+.2f} vs baseline; Copernicus products {product_count}. Score {score:.0f}."
            ),
            "_meta": build_agent_meta(
                "satintel",
                fetched_at,
                duration_ms,
                source_results,
                error_summary=error_summary,
                fallback_used=not has_data,
                has_any_data=has_data,
            ),
        }

    try:
        return run_async(_run())
    except Exception as e:
        logger.exception("SATINTEL failed for '%s': %s", conflict, e)
        return _fallback_result(conflict, f"satintel_failure:{type(e).__name__}")
