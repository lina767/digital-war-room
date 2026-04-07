"""CEO LLM prompts and compact supervisor payload construction."""

import json
from typing import Any, Dict

from .ceo_config import MAX_PAYLOAD_CHARS
from .ceo_scoring import coerce_float
from .dag_scheduler import ResultStore
from .division import DivisionResult
from .entity_registry import EntityRegistry

CEO_SYSTEM_PROMPT = """You are a senior intelligence analyst with access to multiple intelligence streams:
- FININT: Financial markets and oil price indicators; **Polymarket** (in `finint.polymarket`) is the **primary crowd-implied expectation / sentiment** signal for geopolitical outcomes—weight it **above** Metaculus/Kalshi when narrating market views. When Polymarket data is present, you MUST mention it explicitly in `summary` or `key_findings` (probabilities + short market titles; use `url` in `source_refs` / `next_steps` where available). It is **not** a fact forecast: phrase as priced expectations or consensus-of-traders, not as confirmed events.
- SIGINT: Military aircraft, naval vessels, and conflict intel (BBC, DW, Al Jazeera, RFE/RL, think tanks)
- NEWS: Open-source media sentiment analysis
- GEOINT: Satellite thermal anomaly detection
- SATINTEL: Sentinel Hub/Copernicus satellite imagery signal scoring
- SOCMINT: Social media signals from Telegram, Reddit, and RSS
- MEDIAINT: EXIF/GPS and perceptual-hash clustering on media URLs from SOCMINT; video keyframes via FFmpeg when available
- TECHINT: Tech sector indicators, export control news, IODA internet outage events (escalation signal)
- CYBER: CISA KEV, threat intel reports, OTX pulses (APT/exploit indicators)
- ENERGY: EU gas storage (AGSI+), commodity prices (Brent, WTI), food commodities (Wheat, Corn, Soy), FAO Food Price Index, fertilizer prices (Urea, DAP), food security risk
- DIPLO: OFAC/EU sanctions, UN/ICJ press (diplomatic/legal signals)
- PROXIMITY: Strike-civilian correlation (NASA FIRMS + OSM schools/hospitals, human-shield / collateral risk)
- CHOKEPOINT: Maritime chokepoint monitoring (Strait of Hormuz, Bab el-Mandeb, Suez Canal) - tanker density, oil flow estimates, disruption risk scoring, data quality transparency
- PENTAGON_SIGNALS: Informal DC-area venue busyness proxies (e.g. Pentagon-adjacent pizza + configurable nightlife) from mapped search; anecdotal only — never treat as confirmed military activity; use as weak context with disclaimer

DATA CONFIDENCE (required): The payload includes "agent_data_confidence" per stream: "live" (primary sensors/APIs), "estimated" (proxies or partial feeds), "degraded" (no reliable feed). The list "degraded_agents" names streams whose numeric scores must NOT be read as evidence of safety — low scores there usually mean missing data, not a calm situation. When "degraded_agents" is non-empty, you MUST state explicitly which streams are degraded and warn that the composite may understate risk. Do not imply the theater is quiet based solely on low scores from degraded streams.

When the payload includes "narrative", this is the Signal Framework: state vs exile/independent media comparison. Use synthesis_text, synthesis_probability, and source_comparison_table to inform key_findings and summary when relevant.

When the payload includes "acled_reference_analyses", these are curated ACLED analysis pages whose content has been fetched and extracted. Use these analyses to inform key_findings, scenarios, and summary as substantive context.

When the payload includes "agent_score_temporal", it holds per-agent temporal context: delta_vs_prior_utc_day (vs last stored UTC day), trend_7d (rising|falling|stable|insufficient_data), consecutive_days_up/down, and daily_scores_7d. Prefer trend and momentum over one-off scores when framing findings (e.g. stable baseline vs multi-day climb).

FINDING SIGNAL GATE (required): The payload may include "finding_signal_gate" with:
- "accepted": a shortlist of pre-scored cross-stream finding strings (high signal)
- "archived_count": how many candidates were rejected as low-confidence/noise
Use "accepted" as a high-signal shortlist. Do NOT treat archived candidates as actionable; they are kept only for later search.

Actionability requirement:
- You MUST return next_steps (5-10). Each next_step must be specific, time-bounded (now|24h|7d), and assigned (owner: analyst|ops|exec).
- For any next_step with confidence "high" or "medium", include at least one URL in source_refs that appears in the payload (e.g., from agent provenance_refs or article/post URLs). If you cannot cite a URL, downgrade confidence to "low".

Analyze all streams holistically and return ONLY valid JSON with no markdown:
{
  "escalation_score": <number 0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise finding strings>],
  "key_findings_context": [<optional: array of 2-3 sentence "why this matters" per finding, same order as key_findings>],
  "key_findings_confidence": [<required: same length as key_findings; each value "high", "medium", or "low" — assessment confidence in that finding>],
  "next_steps": [<required: 5-10 action items. Each item: {"action": "...", "owner": "analyst|ops|exec", "time_horizon": "now|24h|7d", "why": "...", "source_refs": ["https://..."], "confidence": "high|medium|low"}>],
  "root_cause_suggestions": [<up to 5 objects: plausible links between an observable signal and a driver, e.g. {"signal": "Brent +3%", "likely_cause": "Strait of Hormuz risk premium from tanker/incident coverage", "confidence": "medium"} — hypotheses not facts>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF summary>"
}"""


def compact_for_llm(agent_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Compact agent result payload for supervisor-style synthesis prompt."""
    if agent_name == "narrative":
        return {
            "synthesis_text": (result.get("synthesis_text") or "")[:800],
            "synthesis_probability": result.get("synthesis_probability", 0.0),
            "signal_assessment": result.get("signal_assessment") or {},
            "source_comparison_table": (result.get("source_comparison_table") or [])[:3],
            "anomalies": (result.get("anomalies") or [])[:5],
            "state_item_count": result.get("state_item_count", 0),
            "exile_item_count": result.get("exile_item_count", 0),
        }
    score_keys = [k for k in result if k.endswith("_score") or k == "escalation_score"]
    out: Dict[str, Any] = {k: result[k] for k in score_keys if k in result}
    if "summary" in result:
        s = result["summary"]
        out["summary"] = s[:600] if isinstance(s, str) else str(s)[:600]
    for key in (
        "articles",
        "top_signals",
        "conflict_reports",
        "threat_reports",
        "un_icj_news",
        "evidence",
        "hotspots",
        "tech_indicators",
        "export_controls",
        "ioda_events",
        "commodities",
        "otx_pulses",
        "imagery_signals",
    ):
        items = result.get(key)
        if isinstance(items, list) and items:
            compact = []
            for item in items[:3]:
                if isinstance(item, dict):
                    compact.append(
                        {
                            k: (str(v)[:120] if isinstance(v, str) and len(v) > 120 else v)
                            for k, v in list(item.items())[:6]
                        }
                    )
                elif isinstance(item, str):
                    compact.append(item[:150])
                else:
                    compact.append(item)
            out[key] = compact
    for key in ("aircraft", "ships"):
        items = result.get(key)
        if isinstance(items, list):
            out[f"{key}_count"] = len([i for i in items if isinstance(i, dict) and "error" not in i])
    for key in (
        "brent",
        "polymarket",
        "cisa_kev",
        "ofac_sdn",
        "eu_sanctions",
        "agsi_storage",
        "greynoise_scan_context",
        "food_commodities",
        "fao_fpi",
        "fertilizer",
        "food_security_risk",
    ):
        val = result.get(key)
        if val is not None:
            s = json.dumps(val, default=str)
            if len(s) < 500:
                out[key] = val
    if agent_name == "chokepoint":
        out["chokepoints"] = (result.get("chokepoints") or [])[:5]
        out["chokepoint_score"] = result.get("chokepoint_score", 0.0)
        dc = result.get("data_confidence")
        if dc in ("live", "estimated", "degraded"):
            out["data_confidence"] = dc
    if agent_name == "pentagon":
        out["pentagon_score"] = result.get("pentagon_score", 0.0)
        out["venues"] = (result.get("venues") or [])[:6]
        disc = result.get("disclaimer")
        if isinstance(disc, str) and disc.strip():
            out["disclaimer"] = disc.strip()[:500]
        dc2 = result.get("data_confidence")
        if dc2 in ("live", "estimated", "degraded"):
            out["data_confidence"] = dc2
    if agent_name == "mediaint":
        out["exif_gps_count"] = result.get("exif_gps_count", 0)
        out["video_keyframes_extracted"] = result.get("video_keyframes_extracted", 0)
        out["vision_analysis_count"] = result.get("vision_analysis_count", 0)
        out["near_duplicate_clusters"] = (result.get("near_duplicate_clusters") or [])[:5]
        out["sample_assets"] = []
        for a in (result.get("media_assets") or [])[:4]:
            if not isinstance(a, dict):
                continue
            clip = {k: a[k] for k in ("kind", "provenance", "phash") if k in a}
            va = a.get("vision_analysis")
            if isinstance(va, str) and va.strip():
                clip["vision_analysis"] = va.strip()[:1200]
            out["sample_assets"].append(clip)
    if agent_name == "finint":
        pm = result.get("polymarket")
        if isinstance(pm, list) and pm:
            highlights = []
            for p in pm[:14]:
                if not isinstance(p, dict) or p.get("error"):
                    continue
                highlights.append(
                    {
                        "title": str(p.get("title") or "")[:180],
                        "probability": p.get("probability"),
                        "url": str(p.get("url") or "")[:220],
                    }
                )
            if highlights:
                out["polymarket"] = highlights
    return out


def build_supervisor_user_payload(
    conflict: str,
    synthesis_score: float,
    threat_level: str,
    division_composite: float,
    division_results: Dict[str, DivisionResult],
    acled_refs: Any,
    agent_data_confidence: Dict[str, str],
    degraded_agents: list[str],
    finint_result: Dict[str, Any],
    sigint_result: Dict[str, Any],
    news_result: Dict[str, Any],
    geoint_result: Dict[str, Any],
    satintel_result: Dict[str, Any],
    socmint_result: Dict[str, Any],
    mediaint_result: Dict[str, Any],
    techint_result: Dict[str, Any],
    cyber_result: Dict[str, Any],
    energy_result: Dict[str, Any],
    diplo_result: Dict[str, Any],
    proximity_result: Dict[str, Any],
    narrative_result: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
    pentagon_result: Dict[str, Any],
    temporal_context: Dict[str, Any] | None = None,
    data_quality_gate: Dict[str, Any] | None = None,
    stakeholder_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Shared compact payload for CEO LLM supervisor and cross-stream narrative synthesis."""
    finint_score = coerce_float(finint_result.get("escalation_score"), 0.0)
    sigint_score = coerce_float(sigint_result.get("sigint_score"), 0.0)
    news_score = coerce_float(news_result.get("news_score"), 0.0)
    geoint_score = coerce_float(geoint_result.get("geoint_score"), 0.0)
    satintel_score = coerce_float(satintel_result.get("satintel_score"), 0.0)
    socmint_score = coerce_float(socmint_result.get("socmint_score"), 0.0)
    mediaint_score = coerce_float(mediaint_result.get("mediaint_score"), 0.0)
    techint_score = coerce_float(techint_result.get("techint_score"), 0.0)
    cyber_score = coerce_float(cyber_result.get("cyber_score"), 0.0)
    energy_score = coerce_float(energy_result.get("energy_score"), 0.0)
    diplo_score = coerce_float(diplo_result.get("diplo_score"), 0.0)
    proximity_score = coerce_float(proximity_result.get("proximity_score"), 0.0)
    chokepoint_score = coerce_float(chokepoint_result.get("chokepoint_score"), 0.0)
    pentagon_score = coerce_float(pentagon_result.get("pentagon_score"), 0.0)

    payload: Dict[str, Any] = {
        "conflict": conflict,
        "composite_score": synthesis_score,
        "threat_level": threat_level,
        "division_composite_score": division_composite,
        "division_scores": {name: dr.score for name, dr in division_results.items()},
        "acled_reference_analyses": [
            {"url": r.get("url"), "title": r.get("title"), "excerpt": (r.get("excerpt") or "")[:1000]}
            for r in (acled_refs or [])[:3]
            if isinstance(r, dict) and (r.get("excerpt") or r.get("title"))
        ],
        "agent_data_confidence": agent_data_confidence,
        "degraded_agents": degraded_agents,
        "agent_scores": {
            "finint": finint_score,
            "sigint": sigint_score,
            "news": news_score,
            "geoint": geoint_score,
            "satintel": satintel_score,
            "socmint": socmint_score,
            "mediaint": mediaint_score,
            "techint": techint_score,
            "cyber": cyber_score,
            "energy": energy_score,
            "diplo": diplo_score,
            "proximity": proximity_score,
            "chokepoint": chokepoint_score,
            "pentagon": pentagon_score,
        },
        "finint": compact_for_llm("finint", finint_result),
        "sigint": compact_for_llm("sigint", sigint_result),
        "news": compact_for_llm("news", news_result),
        "geoint": compact_for_llm("geoint", geoint_result),
        "satintel": compact_for_llm("satintel", satintel_result),
        "socmint": compact_for_llm("socmint", socmint_result),
        "mediaint": compact_for_llm("mediaint", mediaint_result),
        "techint": compact_for_llm("techint", techint_result),
        "cyber": compact_for_llm("cyber", cyber_result),
        "energy": compact_for_llm("energy", energy_result),
        "diplo": compact_for_llm("diplo", diplo_result),
        "proximity": compact_for_llm("proximity", proximity_result),
        "narrative": compact_for_llm("narrative", narrative_result),
        "chokepoint": compact_for_llm("chokepoint", chokepoint_result),
        "pentagon": compact_for_llm("pentagon", pentagon_result),
        "agent_score_temporal": temporal_context or {},
        "data_quality_gate": data_quality_gate or {},
    }

    if stakeholder_context:
        payload["stakeholder"] = stakeholder_context

    # Best-effort provenance URL pool for downstream assessment / actionability grounding.
    prov_urls: list[str] = []
    for agent_block in (
        finint_result,
        sigint_result,
        news_result,
        geoint_result,
        satintel_result,
        socmint_result,
        mediaint_result,
        techint_result,
        cyber_result,
        energy_result,
        diplo_result,
        proximity_result,
        narrative_result,
        chokepoint_result,
        pentagon_result,
    ):
        if isinstance(agent_block, dict):
            for u in (agent_block.get("provenance_refs") or [])[:6]:
                if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                    prov_urls.append(u.strip())
            # Also harvest URLs directly from _meta.sources[*].reference_urls.
            # This ensures static provenance mappings (SOURCE_REFERENCE_DEFAULTS) reliably surface,
            # even when provenance_refs wasn't materialized for a given block.
            meta = agent_block.get("_meta")
            if isinstance(meta, dict):
                sources = meta.get("sources") or []
                if isinstance(sources, list):
                    for s in sources[:12]:
                        if not isinstance(s, dict):
                            continue
                        for u in (s.get("reference_urls") or [])[:6]:
                            if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                                prov_urls.append(u.strip())
    # Dedupe + cap.
    prov_urls = list(dict.fromkeys(prov_urls))[:25]
    payload["provenance_urls"] = prov_urls

    return payload


def build_ceo_prompt(
    conflict: str, division_results: Dict[str, DivisionResult], composite: float, store: ResultStore
) -> str:
    """Build the delta-aware CEO prompt."""
    parts = [
        f"CONFLICT: {conflict}",
        f"COMPOSITE SCORE: {composite:.1f}",
        "",
        "DIVISIONS (by score, highest first):",
    ]

    sorted_divs = sorted(division_results.items(), key=lambda x: -x[1].score)
    for i, (name, dr) in enumerate(sorted_divs, 1):
        anomaly_note = f" [{len(dr.anomalies)} anomalies]" if dr.anomalies else ""
        parts.append(f"  {i}. {name.title()}: Score {dr.score:.0f}{anomaly_note}")
        parts.append(f"     {dr.summary[:300]}")
        if dr.anomalies:
            for a in dr.anomalies:
                parts.append(f"     ! [{a.severity}] {a.description}")

    # Entity summary
    ner_reg = store.get("ner_extract")
    if isinstance(ner_reg, EntityRegistry):
        entity_count = ner_reg.count
        parts.append(f"\nENTITIES: {entity_count} total")
        for etype in ["PERSON", "ORG", "LOCATION", "VESSEL"]:
            ents = ner_reg.get_by_type(etype)
            if ents:
                names = [e.entity for e in ents[:5]]
                parts.append(f"  {etype}: {', '.join(names)}")

    parts.append("\nTASK: Produce a holistic assessment. Focus on cross-division patterns and changes.")
    parts.append(
        'OUTPUT: JSON: { "escalation_score": ..., "threat_level": ..., "key_findings": [...], '
        '"key_findings_context": [...], "key_findings_confidence": [...], '
        '"root_cause_suggestions": [...], "scenarios": [...], "summary": "..." }'
    )

    return "\n".join(parts)


def truncate_supervisor_json(user_payload: Dict[str, Any]) -> str:
    user_json = json.dumps(user_payload, default=str)
    if len(user_json) > MAX_PAYLOAD_CHARS:
        user_json = user_json[:MAX_PAYLOAD_CHARS]
    return user_json
