"""
GEOINT Agent orchestration.

Data fetching/parsing lives in fetchers/geoint_fetchers.py.
Scoring logic lives in scorers/geoint_scorer.py.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .context import AgentContext

from services.acled_auth import has_acled_oauth

from .fetchers.geoint_fetchers import (
    HAPI_APP_IDENTIFIER,
    _fetch_thermal_anomalies_for_focus_regions,
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
from .utils import ProcessingStep, SourceResult, build_agent_meta, safe_float, utc_now_iso

logger = logging.getLogger(__name__)
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

Scoring:
- Base: 20
- High-confidence anomaly: +5 each (max +40)
- Explosion-type (FRP>500): +15 each (max +45)
- Cluster (3+ anomalies within 0.5°): +20
- Recent (acquired within last 6h): +5 per anomaly
- More than 10 anomalies: +10
- Clamp to [0, 100]

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

        raw = get_thermal_anomalies(region=region, days=3)
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

        reliefweb_raw = get_conflict_hotspot_news(conflict=conflict)
        reliefweb_reports = [
            r
            for r in (reliefweb_raw if isinstance(reliefweb_raw, list) else [])
            if isinstance(r, dict) and "error" not in r
        ]

        has_acled_cfg = has_acled_oauth() or os.getenv("ACLED_API_KEY")
        has_acled_reports = any(r.get("source") == "ACLED" for r in reliefweb_reports)

        eo_links = get_eo_browser_links(conflict=conflict)
        if not isinstance(eo_links, dict):
            eo_links = {}

        gdelt_geo_countries = get_gdelt_geo_countries(conflict=conflict)
        score, explosion_count, clusters, _ = compute_geoint_score(anomalies)
        high = sum(1 for a in anomalies if a.get("confidence") == "high")
        hotspots = sorted(anomalies, key=lambda x: _safe_float(x.get("frp"), 0), reverse=True)[:5]

        summary_extra = ""
        if gdelt_geo_countries:
            summary_extra += f" GDELT GEO: {len(gdelt_geo_countries)} countries."
        if has_acled_cfg and not has_acled_reports:
            summary_extra += " ACLED data unavailable or empty; score based mainly on thermal anomalies and ReliefWeb."

        duration_ms = int((time.perf_counter() - start) * 1000)
        hapi_count = sum(
            1 for r in reliefweb_reports if isinstance(r, dict) and (r.get("source") or "").startswith("HDX HAPI")
        )
        gdacs_count = sum(1 for r in reliefweb_reports if isinstance(r, dict) and (r.get("source") or "") == "GDACS")

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
                status="ok",
                fetched_at=fetched_at,
                record_count=gdacs_count,
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
            ProcessingStep(step="fetch_thermal_and_hotspot_news", at=fetched_at),
            ProcessingStep(step="eo_browser_gdelt_geo", at=fetched_at),
            ProcessingStep(step="score_hotspots_clusters", at=fetched_at),
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
