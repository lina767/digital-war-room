"""
SIGINT Agent (orchestration only).

Fetching/parsing lives in fetchers/sigint_fetchers.py.
Score computation lives in scorers/sigint_scorer.py.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .contracts import get_agent_fallback
from .fetchers.sigint_fetchers import (
    TARGET_AIRCRAFT,
    get_conflict_reports as fetcher_get_conflict_reports,
    get_military_aircraft as fetcher_get_military_aircraft,
    get_naval_vessels as fetcher_get_naval_vessels,
    get_target_aircraft as fetcher_get_target_aircraft,
)
from .health_registry import get_health_registry
from .iaea_tracker import fetch_notams
from .llm import run_agent_with_fallback
from .scorers.sigint_scorer import compute_sigint_score
from .utils import (
    ProcessingStep,
    ScoreConfidence,
    SourceResult,
    build_agent_meta,
    utc_now_iso,
)


class SigintResult(BaseModel):
    conflict: str
    aircraft: List[Dict[str, Any]] = Field(default_factory=list)
    ships: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tankers: List[Dict[str, Any]] = Field(default_factory=list)
    hormuz_tanker_count: int = 0
    conflict_reports: List[Dict[str, Any]] = Field(default_factory=list)
    notams: List[Dict[str, Any]] = Field(default_factory=list)
    sigint_score: float = 0.0
    alerts: List[str] = Field(default_factory=list)
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=utc_now_iso)
    target_tracks: Dict[str, Any] = Field(default_factory=dict)


def _run_rule_based_sigint(conflict: str) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            fut_air = executor.submit(fetcher_get_military_aircraft)
            fut_reports = executor.submit(fetcher_get_conflict_reports, conflict)
            fut_notams = executor.submit(lambda: fetch_notams(days=3, limit=15))
            target_names = list(TARGET_AIRCRAFT.keys())
            fut_targets = [executor.submit(fetcher_get_target_aircraft, name) for name in target_names]

            try:
                raw_aircraft = fut_air.result(timeout=40)
            except Exception as e:
                raw_aircraft = [{"error": str(e)}]

            raw_ships: List[Dict[str, Any]] = fetcher_get_naval_vessels()

            try:
                raw_reports = fut_reports.result(timeout=40)
            except Exception as e:
                raw_reports = [{"error": str(e)}]

            try:
                notam_result = fut_notams.result(timeout=40)
            except Exception as e:
                notam_result = {"notams": [], "error": str(e)}

            target_tracks: Dict[str, Any] = {}
            for name, fut in zip(target_names, fut_targets, strict=True):
                try:
                    target_tracks[name] = fut.result(timeout=40)
                except Exception as e:
                    target_tracks[name] = {"target": name, "error": str(e)}

        aircraft = [a for a in (raw_aircraft or []) if isinstance(a, dict) and "error" not in a]
        ships = [s for s in (raw_ships or []) if isinstance(s, dict) and "error" not in s]
        reports = [r for r in (raw_reports or []) if isinstance(r, dict) and "error" not in r]
        notams = (notam_result.get("notams") or []) if isinstance(notam_result, dict) else []
        hormuz_tankers: List[Dict[str, Any]] = []

        score = compute_sigint_score(aircraft, ships, reports)

        alerts: List[str] = []
        if aircraft:
            by_cat: Dict[str, List] = {}
            for a in aircraft:
                by_cat.setdefault(a.get("category", "?"), []).append(a.get("flight", "?"))
            if "doomsday" in by_cat:
                alerts.append(
                    f"⚠ {len(by_cat['doomsday'])} DOOMSDAY/NUCLEAR C3 aircraft: {', '.join(by_cat['doomsday'][:5])} — highest escalation signal"
                )
            if "iranian_gov" in by_cat:
                alerts.append(
                    f"🇮🇷 {len(by_cat['iranian_gov'])} Iranian gov/IRGC aircraft: {', '.join(by_cat['iranian_gov'][:5])}"
                )
            for cat, flights in by_cat.items():
                if cat in ("doomsday", "iranian_gov"):
                    continue
                alerts.append(f"{len(flights)} {cat} aircraft: {', '.join(flights[:3])}")
        if ships:
            alerts.append(f"{len(ships)} warship(s) in region")
        if reports:
            alerts.append(f"{len(reports)} recent intel reports")
        if notams:
            alerts.append(f"{len(notams)} NOTAM(s) (airspace)")

        sources_ok: List[str] = []
        sources_missing: List[str] = []
        for name, data in (
            ("aircraft", aircraft),
            ("ships", ships),
            ("conflict_reports", reports),
            ("notams", notams),
        ):
            if data:
                sources_ok.append(name)
            else:
                sources_missing.append(name)
        for tname, tdata in target_tracks.items():
            if (
                isinstance(tdata, dict)
                and not tdata.get("error")
                and (tdata.get("adsbx") or tdata.get("adsbexchange_rapidapi") or tdata.get("fallback_sigint") or tdata.get("opensky"))
            ):
                sources_ok.append(f"target_{tname}")
        score_confidence = ScoreConfidence(
            level="high" if len(sources_ok) >= 2 else "low",
            sources_ok=sources_ok,
            sources_missing=sources_missing,
        )

        result = SigintResult(
            conflict=conflict,
            aircraft=aircraft,
            ships=ships,
            hormuz_tankers=hormuz_tankers,
            hormuz_tanker_count=len(hormuz_tankers),
            conflict_reports=reports,
            notams=notams,
            sigint_score=round(score, 1),
            alerts=alerts,
            summary=f"SIGINT (rule-based): {len(aircraft)} aircraft, {len(ships)} ships, {len(hormuz_tankers)} Hormuz tankers, {len(reports)} reports, {len(notams)} NOTAMs. Score {score:.0f}.",
            score_confidence=score_confidence,
            target_tracks=target_tracks,
        )
        out = result.model_dump(mode="json")

        duration_ms = int((time.perf_counter() - start) * 1000)
        adsb_has_error = any(isinstance(a, dict) and a.get("error") for a in (raw_aircraft or []))
        adsbx_hits = 0
        for a in aircraft:
            src = (a.get("source") or "").lower()
            if src in ("adsbexchange", "adsbx", "adsbexchange_rapidapi"):
                adsbx_hits += 1
        for tdata in target_tracks.values():
            if isinstance(tdata, dict) and tdata.get("adsbx"):
                adsbx_hits += 1
        source_results = [
            SourceResult(name="ADS-B", status="error" if adsb_has_error else "ok", fetched_at=fetched_at, record_count=len(aircraft)),
            SourceResult(name="ADSBexchange", status="ok", fetched_at=fetched_at, record_count=adsbx_hits),
            SourceResult(name="Conflict Reports", status="ok" if reports else "error", fetched_at=fetched_at, record_count=len(reports)),
            SourceResult(name="NOTAMs", status="error" if (isinstance(notam_result, dict) and notam_result.get("error")) else "ok", fetched_at=fetched_at, record_count=len(notams)),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "sigint", sr)
        out["_meta"] = build_agent_meta(
            "sigint",
            fetched_at,
            duration_ms,
            source_results,
            error_summary=(f"{len(sources_missing)} source(s) missing" if sources_missing else None),
            has_any_data=bool(aircraft or ships or reports or notams),
            processing_steps=[ProcessingStep(step="fetch_adsb_reports_notams", at=fetched_at), ProcessingStep(step="compute_sigint_score", at=fetched_at)],
        )
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fb = get_agent_fallback("sigint")
        fb["conflict"] = conflict
        fb["sigint_score"] = 30.0
        fb["summary"] = "SIGINT error: pipeline failed."
        fb["_meta"] = build_agent_meta(
            "sigint",
            fetched_at,
            duration_ms,
            [],
            fallback_used=True,
            error_summary=str(e),
            has_any_data=False,
            processing_steps=[ProcessingStep(step="error_fallback", at=fetched_at)],
        )
        return fb


SIGINT_SYSTEM = """You are a SIGINT analyst monitoring military movements and conflict activity.
Call all three tools, compute a score (0-100), return ONLY valid JSON:

Scoring:
- Base: 30
- Surveillance aircraft: +10 each (max +40)
- Tanker aircraft (strike prep): +8 each
- Fighter aircraft: +12 each
- Warships: +5 each (max +25)
- Conflict reports (airstrikes, attacks): +8 each (max +30)
- Clamp to [0, 100]

{
  "aircraft": [...],
  "ships": [...],
  "conflict_reports": [...],
  "sigint_score": <number>,
  "alerts": ["<alert>", ...],
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


_SIGINT_TOOL_FNS = {
    "get_military_aircraft": fetcher_get_military_aircraft,
    "get_naval_vessels": fetcher_get_naval_vessels,
    "get_conflict_reports": fetcher_get_conflict_reports,
}
_SIGINT_TOOL_SCHEMAS = [
    {"name": "get_military_aircraft", "description": "Fetch military aircraft in conflict regions via ADS-B.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_naval_vessels", "description": "Fetch naval vessels in conflict regions.", "input_schema": {"type": "object", "properties": {}}},
    {
        "name": "get_conflict_reports",
        "description": "Fetch conflict intelligence reports from RSS feeds.",
        "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
    },
]


def run_sigint_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return run_agent_with_fallback(
        conflict,
        rule_based_fn=_run_rule_based_sigint,
        system_prompt=SIGINT_SYSTEM,
        user_content_template="Monitor military movements for conflict: {conflict}",
        tool_fns=_SIGINT_TOOL_FNS,
        tool_schemas=_SIGINT_TOOL_SCHEMAS,
        max_rounds=6,
    )
