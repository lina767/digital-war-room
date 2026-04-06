"""
GEOINT Agent orchestration.

Data fetching/parsing lives in fetchers/geoint_fetchers.py.
Scoring logic lives in scorers/geoint_scorer.py.
"""

import asyncio
import logging
import os
import time
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .context import AgentContext

from services.acled_auth import has_acled_oauth
from services.pg_sync import connection, use_postgres

from .fetchers.geoint_fetchers import (
    HAPI_APP_IDENTIFIER,
    _fetch_thermal_anomalies_for_focus_regions,
    fetch_gdelt_doc_summary,
    get_conflict_events_for_heatmap,
    get_conflict_hotspot_news,
    get_conflict_region,
    get_eo_browser_links,
    get_gdelt_geo_countries,
    get_thermal_anomalies,
    get_theater_events,
)
from .health_registry import get_health_registry
from .llm import run_agent_with_fallback
from .scorers.geoint_scorer import compute_geoint_score, enrich_geoint_with_ner_entities
from .utils import ProcessingStep, SourceResult, build_agent_meta, run_async, safe_float, utc_now_iso

logger = logging.getLogger(__name__)


def _unwrap_gather(name: str, result: Any, default: Any) -> Any:
    if isinstance(result, Exception):
        logger.warning("GEOINT parallel fetch %s failed: %s", name, result)
        return default
    return result


def _ensure_geoint_baseline_table(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS geoint_firms_daily (
            region TEXT NOT NULL,
            day DATE NOT NULL,
            anomaly_count INTEGER NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (region, day)
        )
        """
    )


def _read_geoint_baseline(region: str, days: int = 30) -> Optional[float]:
    if not use_postgres():
        return None
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                _ensure_geoint_baseline_table(cur)
                conn.commit()
                start = date.today() - timedelta(days=days)
                cur.execute(
                    """
                    SELECT AVG(anomaly_count)::double precision
                    FROM geoint_firms_daily
                    WHERE region = %s
                      AND day >= %s
                      AND day < CURRENT_DATE
                    """,
                    (region, start),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return float(row[0])
    except Exception:
        logger.debug("GEOINT baseline read failed", exc_info=True)
    return None


def _write_geoint_baseline(region: str, anomaly_count: int) -> None:
    if not use_postgres():
        return
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                _ensure_geoint_baseline_table(cur)
                cur.execute(
                    """
                    INSERT INTO geoint_firms_daily (region, day, anomaly_count, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (region, day) DO UPDATE SET
                        anomaly_count = EXCLUDED.anomaly_count,
                        updated_at = NOW()
                    """,
                    (region, date.today(), int(anomaly_count)),
                )
                conn.commit()
    except Exception:
        logger.debug("GEOINT baseline write failed", exc_info=True)


async def _fetch_geoint_sources_parallel(
    conflict: str, region: str
) -> Tuple[Any, Any, Any, Any, Any, Any]:
    return await asyncio.gather(
        asyncio.to_thread(get_thermal_anomalies, region, 3),
        asyncio.to_thread(get_conflict_hotspot_news, conflict),
        asyncio.to_thread(get_eo_browser_links, conflict),
        asyncio.to_thread(get_gdelt_geo_countries, conflict),
        asyncio.to_thread(fetch_gdelt_doc_summary, conflict),
        asyncio.to_thread(get_conflict_events_for_heatmap, conflict, 200),
        return_exceptions=True,
    )


def _safe_float(v: Any, default: float = 0.0) -> float:
    result = safe_float(v)
    return result if result is not None else default


GEOINT_SYSTEM = """You are a GEOINT (Geospatial Intelligence) analyst using NASA FIRMS, ReliefWeb/ACLED, and EO Browser links.
Your job: get conflict region, fetch thermal anomalies (days=3), conflict hotspot news, and EO Browser links for the region (Lebanon, Iran, etc.); then compute score.

Steps:
1. Call get_conflict_region(conflict)
2. Call get_thermal_anomalies(region=..., days=3)
3. Call get_conflict_hotspot_news(conflict)
4. Call get_eo_browser_links(conflict) for Sentinel Hub EO Browser URLs
5. Compute score and return JSON

Scoring (align with rule-based pipeline):
- Final geoint_score uses weighted factors: ~40% thermal (FIRMS clusters, FRP, recency), ~30% ACLED/conflict density,
  ~15% GDACS disaster alerts, ~15% CrisisWatch trend text; optional FIRMS-vs-ACLED hex corroboration boosts confidence.
- Thermal component: base 20; high-conf +5 each (cap +40); explosion-type +15 each (cap +45); DBSCAN-style clusters +20;
  recent acquisitions +5 each; >10 anomalies +10; subscore clamped 0-100.

Return ONLY valid JSON:
{
  "anomalies": [...],
  "anomaly_count": <number>,
  "high_confidence_count": <number>,
  "explosion_count": <number>,
  "clusters": [{"center_lat": ..., "center_lon": ..., "count": N}],
  "geoint_score": <number>,
  "hotspots": [top 5 by FRP],
  "reliefweb_reports": [...],
  "eo_browser_links": {"region": "...", "eo_browser_url": "...", "description": "..."},
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""
def _empty_result(conflict: str, error_summary: str | None = None) -> Dict[str, Any]:
    fetched_at = utc_now_iso()
    return {
        "conflict": conflict,
        "anomalies": [],
        "anomaly_count": 0,
        "high_confidence_count": 0,
        "explosion_count": 0,
        "clusters": [],
        "geoint_score": 20.0,
        "hotspots": [],
        "reliefweb_reports": [],
        "eo_browser_links": {},
        "gdelt_geo_countries": [],
        "gdelt_bigquery": {},
        "gdelt_doc_summary": {},
        "summary": "No thermal anomaly data available.",
        "_meta": build_agent_meta(
            "geoint",
            fetched_at,
            0,
            [],
            fallback_used=True,
            error_summary=error_summary or "No data",
            has_any_data=False,
            processing_steps=[ProcessingStep(step="no_data_fallback", at=fetched_at)],
        ),
    }


def _run_rule_based_geoint(conflict: str, context: Optional["AgentContext"] = None) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        region = get_conflict_region(conflict=conflict)
        if not isinstance(region, str):
            region = "middle_east"

        baseline_avg = _read_geoint_baseline(region, days=30)

        raw, reliefweb_raw, eo_links, gdelt_geo_countries, gdelt_bq, acled_heatmap_raw = run_async(
            _fetch_geoint_sources_parallel(conflict, region)
        )
        raw = _unwrap_gather("NASA FIRMS", raw, [{"error": "parallel fetch failed"}])
        reliefweb_raw = _unwrap_gather("ReliefWeb/ACLED", reliefweb_raw, [])
        eo_links = _unwrap_gather("EO Browser", eo_links, {})
        gdelt_geo_countries = _unwrap_gather("GDELT GEO", gdelt_geo_countries, [])
        gdelt_bq = _unwrap_gather("GDELT DOC timeline", gdelt_bq, {"ok": False, "error": "parallel fetch failed"})
        acled_heatmap_raw = _unwrap_gather("ACLED heatmap", acled_heatmap_raw, [])

        anomalies = [a for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and "error" not in a]

        if context and getattr(context, "focus_regions", None):
            extra = _fetch_thermal_anomalies_for_focus_regions(getattr(context, "focus_regions", []), days=3)
            seen = {(round(_safe_float(a.get("lat"), 0), 2), round(_safe_float(a.get("lon"), 0), 2)) for a in anomalies}
            for a in extra:
                if not isinstance(a, dict) or "error" in a:
                    continue
                key = (round(_safe_float(a.get("lat"), 0), 2), round(_safe_float(a.get("lon"), 0), 2))
                if key not in seen:
                    seen.add(key)
                    a["source"] = "handoff_focus"
                    anomalies.append(a)

        reliefweb_reports = [
            r
            for r in (reliefweb_raw if isinstance(reliefweb_raw, list) else [])
            if isinstance(r, dict) and "error" not in r
        ]

        has_acled_cfg = has_acled_oauth() or os.getenv("ACLED_API_KEY")
        has_acled_reports = any(r.get("source") == "ACLED" for r in reliefweb_reports)

        if not isinstance(eo_links, dict):
            eo_links = {}

        if not isinstance(gdelt_bq, dict):
            gdelt_bq = {"ok": False, "error": "invalid response"}

        acled_events = [
            e
            for e in (acled_heatmap_raw if isinstance(acled_heatmap_raw, list) else [])
            if isinstance(e, dict) and "error" not in e
        ]

        gdacs_count = sum(
            1 for r in reliefweb_reports if isinstance(r, dict) and (r.get("source") or "") == "GDACS"
        )

        score, explosion_count, clusters, _, score_breakdown = compute_geoint_score(
            anomalies,
            reliefweb_reports=reliefweb_reports,
            acled_events=acled_events,
            gdacs_count=gdacs_count,
            baseline_avg_anomalies=baseline_avg,
        )

        _write_geoint_baseline(region, len(anomalies))
        high = sum(1 for a in anomalies if a.get("confidence") == "high")
        hotspots = sorted(anomalies, key=lambda x: _safe_float(x.get("frp"), 0), reverse=True)[:5]

        summary_extra = ""
        if gdelt_geo_countries:
            summary_extra += f" GDELT GEO: {len(gdelt_geo_countries)} countries."
        if gdelt_bq.get("ok") and gdelt_bq.get("total_matched"):
            summary_extra += (
                f" GDELT DOC timeline: {gdelt_bq['total_matched']} volume points "
                f"(timespan {gdelt_bq.get('timespan', '?')})."
            )
        if has_acled_cfg and not has_acled_reports and not acled_events:
            summary_extra += " ACLED data unavailable or empty; conflict density relies on ReliefWeb/GDACS/CrisisWatch."
        corr = (score_breakdown.get("corroboration") or {}) if isinstance(score_breakdown, dict) else {}
        n_corr = int(corr.get("corroborated_cell_count") or 0)
        if n_corr:
            summary_extra += f" Hex corroboration: {n_corr} cell(s) with FIRMS+ACLED overlap."
        br = score_breakdown.get("baseline_ratio")
        if br is not None and br >= 2.0:
            summary_extra += f" FIRMS ~{br:.1f}× vs 30d baseline."

        duration_ms = int((time.perf_counter() - start) * 1000)
        hapi_count = sum(
            1 for r in reliefweb_reports if isinstance(r, dict) and (r.get("source") or "").startswith("HDX HAPI")
        )
        crisiswatch_count = sum(
            1
            for r in reliefweb_reports
            if isinstance(r, dict) and (r.get("source") or "").startswith("CrisisWatch")
        )

        source_results = [
            SourceResult(
                name="NASA FIRMS",
                status="ok" if anomalies else "error",
                fetched_at=fetched_at,
                record_count=len(anomalies),
            ),
            SourceResult(
                name="ReliefWeb/ACLED",
                status="ok" if reliefweb_reports else "error",
                fetched_at=fetched_at,
                record_count=len(reliefweb_reports),
            ),
            SourceResult(
                name="GDACS",
                status="ok" if gdacs_count else "error",
                fetched_at=fetched_at,
                record_count=gdacs_count,
            ),
            SourceResult(
                name="CrisisWatch",
                status="ok" if crisiswatch_count else "error",
                fetched_at=fetched_at,
                record_count=crisiswatch_count,
            ),
            SourceResult(
                name="EO Browser",
                status="ok" if eo_links else "error",
                fetched_at=fetched_at,
                record_count=len(eo_links) if isinstance(eo_links, dict) else 0,
            ),
            SourceResult(
                name="GDELT GEO",
                status="ok" if gdelt_geo_countries else "error",
                fetched_at=fetched_at,
                record_count=len(gdelt_geo_countries),
            ),
            SourceResult(
                name="GDELT DOC Timeline",
                status="ok"
                if gdelt_bq.get("ok")
                else ("error" if gdelt_bq.get("error") else "degraded"),
                fetched_at=fetched_at,
                record_count=int(gdelt_bq.get("total_matched") or 0) if gdelt_bq.get("ok") else 0,
                endpoint_kind="api",
            ),
        ]
        if HAPI_APP_IDENTIFIER:
            source_results.append(
                SourceResult(
                    name="HDX HAPI",
                    status="ok" if hapi_count else "error",
                    fetched_at=fetched_at,
                    record_count=hapi_count,
                )
            )

        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "geoint", sr)

        sources_missing = [s.name for s in source_results if s.status == "error"]
        error_summary = f"{len(sources_missing)} source(s) failed: {', '.join(sources_missing)}" if sources_missing else None
        has_data = bool(anomalies or reliefweb_reports)

        handoff_note = ""
        if context and getattr(context, "focus_regions", None):
            n_focus = len(getattr(context, "focus_regions", []))
            handoff_note = f" Handoff: {n_focus} SIGINT-derived focus region(s) included."

        geo_steps = [
            ProcessingStep(step="parallel_fetch_geoint_sources", at=fetched_at),
            ProcessingStep(step="score_multifactor_hex_corroboration", at=fetched_at),
        ]

        return {
            "conflict": conflict,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "high_confidence_count": high,
            "explosion_count": explosion_count,
            "clusters": clusters,
            "geoint_score": round(score, 1),
            "hotspots": hotspots,
            "reliefweb_reports": reliefweb_reports,
            "eo_browser_links": eo_links,
            "gdelt_geo_countries": gdelt_geo_countries,
            "gdelt_bigquery": gdelt_bq,
            "gdelt_doc_summary": gdelt_bq,
            "acled_heatmap_events": acled_events[:200],
            "geoint_score_breakdown": score_breakdown,
            "summary": f"GEOINT (rule-based): {len(anomalies)} thermal anomalies ({high} high conf, {explosion_count} explosion-type). {len(clusters)} cluster(s).{summary_extra} EO Browser links included.{handoff_note} Score {score:.0f}.",
            "_meta": build_agent_meta(
                "geoint",
                fetched_at,
                duration_ms,
                source_results,
                error_summary=error_summary,
                has_any_data=has_data,
                processing_steps=geo_steps,
            ),
        }
    except Exception as e:
        logger.exception("GEOINT: rule-based pipeline failed for '%s': %s", conflict, e)
        return _empty_result(conflict, error_summary=str(e))


_GEOINT_TOOL_FNS = {
    "get_conflict_region": get_conflict_region,
    "get_thermal_anomalies": get_thermal_anomalies,
    "get_conflict_hotspot_news": get_conflict_hotspot_news,
    "get_eo_browser_links": get_eo_browser_links,
}

_GEOINT_TOOL_SCHEMAS = [
    {
        "name": "get_conflict_region",
        "description": "Map conflict to a geographic region.",
        "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
    },
    {
        "name": "get_thermal_anomalies",
        "description": "Fetch NASA FIRMS thermal anomalies.",
        "input_schema": {
            "type": "object",
            "properties": {"region": {"type": "string"}, "days": {"type": "integer"}},
            "required": ["region"],
        },
    },
    {
        "name": "get_conflict_hotspot_news",
        "description": "Fetch ReliefWeb/ACLED hotspot news.",
        "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
    },
    {
        "name": "get_eo_browser_links",
        "description": "Generate EO Browser links.",
        "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
    },
]


def enrich_with_ner_entities(geoint_result: Dict[str, Any], entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    return enrich_geoint_with_ner_entities(geoint_result, entities)


def run_geoint_agent(
    conflict: str, context: Optional["AgentContext"] = None, peers: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    def rule_based(c: str):
        return _run_rule_based_geoint(c, context)

    return run_agent_with_fallback(
        conflict,
        rule_based_fn=rule_based,
        system_prompt=GEOINT_SYSTEM,
        user_content_template="Detect thermal anomalies for conflict: {conflict}",
        tool_fns=_GEOINT_TOOL_FNS,
        tool_schemas=_GEOINT_TOOL_SCHEMAS,
        max_rounds=6,
    )
