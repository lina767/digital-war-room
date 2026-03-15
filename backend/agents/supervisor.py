"""
Supervisor – Multi-Agent Orchestrator (no frameworks).
Coordinates 11 agents in parallel, then runs an LLM for final assessment.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Generator, Tuple

import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .llm import call_llm, get_model_name, require_api_key
from .otel_callbacks import traced
from .utils import run_async

_logger = logging.getLogger(__name__)

from .finint_agent import run_finint_agent, enrich_with_ner_entities as finint_enrich_ner
from .geoint_agent import run_geoint_agent, enrich_with_ner_entities as geoint_enrich_ner
from .news_agent import run_news_agent
from .sigint_agent import run_sigint_agent
from .socmint_agent import run_socmint_agent
from .techint_agent import run_techint_agent
from .cyber_agent import run_cyber_agent
from .energy_agent import run_energy_agent
from .protest_agent import run_protest_agent
from .diplo_agent import run_diplo_agent
from .proximity_agent import run_proximity_agent
from .signal_framework_agent import run_signal_framework_agent
from .chokepoint_agent import run_chokepoint_agent, enrich_chokepoints
from .predictive import build_predictive_block
from .acled_reference import fetch_acled_reference_analyses_sync
from .actor_model import build_actors_for_conflict
from .findings_builder import append_agent_findings
from .compliance_enrichment import build_compliance_and_alerts


# Per-agent timeout (seconds). Prevents one slow API from blocking the whole run.
_AGENT_TIMEOUT = 75

# Previous SIGINT data for AIS dark-activity detection across runs.
# Keyed by conflict name, stores last SIGINT result.
_previous_sigint: Dict[str, Dict[str, Any]] = {}
# Timestamp when that result was stored (for AIS gap_hours / last_seen_at).
_previous_sigint_ts: Dict[str, float] = {}


def _result_or_fallback(future, agent_name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return future.result(timeout=_AGENT_TIMEOUT)
    except Exception as e:
        return {**fallback, "error": str(e), "timeout_or_error": True}


def _collect_all_agents(conflict: str) -> Dict[str, Any]:
    """Run all 12 intelligence agents + ACLED reference in parallel."""
    with traced("analysis.collection", {"conflict": conflict}):
        with ThreadPoolExecutor(max_workers=14) as executor:
            futures = {
                "finint":   (executor.submit(run_finint_agent, conflict), {"escalation_score": 0.0, "brent": None, "polymarket": []}),
                "sigint":   (executor.submit(run_sigint_agent, conflict), {"sigint_score": 0.0, "aircraft": [], "ships": [], "conflict_reports": []}),
                "news":     (executor.submit(run_news_agent, conflict), {"news_score": 0.0, "articles": [], "summary": ""}),
                "geoint":   (executor.submit(run_geoint_agent, conflict), {"geoint_score": 0.0, "anomalies": [], "hotspots": []}),
                "socmint":  (executor.submit(run_socmint_agent, conflict), {"socmint_score": 0.0, "top_signals": []}),
                "techint":  (executor.submit(run_techint_agent, conflict), {"techint_score": 0.0, "tech_indicators": [], "ioda_events": [], "ioda_outages": [], "ioda_alerts": [], "ioda_signals_raw": [], "ioda_entities": []}),
                "cyber":    (executor.submit(run_cyber_agent, conflict), {"cyber_score": 0.0, "cisa_kev": {}, "threat_reports": [], "otx_pulses": [], "greynoise_scan_context": {}}),
                "energy":   (executor.submit(run_energy_agent, conflict), {"energy_score": 0.0, "agsi_storage": {}, "commodities": [], "food_commodities": [], "food_security_risk": 0.0}),
                "protest":  (executor.submit(run_protest_agent, conflict), {"protest_score": 0.0, "protest_events": [], "protest_articles": []}),
                "diplo":    (executor.submit(run_diplo_agent, conflict), {"diplo_score": 0.0, "ofac_sdn": {}, "eu_sanctions": {}, "un_icj_news": []}),
                "proximity":(executor.submit(run_proximity_agent, conflict), {"proximity_score": 0.0, "evidence": [], "summary": ""}),
                "narrative": (executor.submit(run_signal_framework_agent, conflict), {"synthesis_text": "", "synthesis_probability": 0.0, "source_comparison_table": [], "signal_assessment": {}, "anomalies": []}),
                "chokepoint": (executor.submit(run_chokepoint_agent, conflict), {"chokepoint_score": 0.0, "chokepoints": [], "summary": ""}),
            }
            acled_ref_f = executor.submit(fetch_acled_reference_analyses_sync, conflict)

            results = {}
            for name, (fut, fallback) in futures.items():
                results[name] = _result_or_fallback(fut, name, fallback)
            acled_refs = _result_or_fallback(acled_ref_f, "acled_reference", [])
            results["acled_refs"] = acled_refs if isinstance(acled_refs, list) else []

    return results


def run_analysis_streaming(conflict: str) -> Generator[Tuple[str, Any], None, None]:
    """
    Run analysis and yield (agent_name, result) as each agent completes, then ("supervisor", final_result).
    Used by GET /api/analyze/stream for SSE progressive rendering.
    """
    _AGENT_FUTURES = [
        ("finint", run_finint_agent, {"escalation_score": 0.0, "brent": None, "polymarket": []}),
        ("sigint", run_sigint_agent, {"sigint_score": 0.0, "aircraft": [], "ships": [], "conflict_reports": []}),
        ("news", run_news_agent, {"news_score": 0.0, "articles": [], "summary": ""}),
        ("geoint", run_geoint_agent, {"geoint_score": 0.0, "anomalies": [], "hotspots": []}),
        ("socmint", run_socmint_agent, {"socmint_score": 0.0, "top_signals": []}),
        ("techint", run_techint_agent, {"techint_score": 0.0, "tech_indicators": [], "ioda_events": [], "ioda_outages": [], "ioda_alerts": [], "ioda_signals_raw": [], "ioda_entities": []}),
        ("cyber", run_cyber_agent, {"cyber_score": 0.0, "cisa_kev": {}, "threat_reports": [], "otx_pulses": [], "greynoise_scan_context": {}}),
        ("energy", run_energy_agent, {"energy_score": 0.0, "agsi_storage": {}, "commodities": [], "food_commodities": [], "food_security_risk": 0.0}),
        ("protest", run_protest_agent, {"protest_score": 0.0, "protest_events": [], "protest_articles": []}),
        ("diplo", run_diplo_agent, {"diplo_score": 0.0, "ofac_sdn": {}, "eu_sanctions": {}, "un_icj_news": []}),
        ("proximity", run_proximity_agent, {"proximity_score": 0.0, "evidence": [], "summary": ""}),
        ("narrative", run_signal_framework_agent, {"synthesis_text": "", "synthesis_probability": 0.0, "source_comparison_table": [], "signal_assessment": {}, "anomalies": []}),
        ("chokepoint", run_chokepoint_agent, {"chokepoint_score": 0.0, "chokepoints": [], "summary": ""}),
    ]
    with traced("analysis.collection.streaming", {"conflict": conflict}):
        with ThreadPoolExecutor(max_workers=14) as executor:
            futures = {name: (executor.submit(fn, conflict), fb) for name, fn, fb in _AGENT_FUTURES}
            acled_f = executor.submit(fetch_acled_reference_analyses_sync, conflict)
            fut_to_name = {f: name for name, (f, _) in futures.items()}
            results: Dict[str, Any] = {}
            for fut in as_completed(list(fut_to_name.keys()) + [acled_f]):
                if fut is acled_f:
                    acled_refs = _result_or_fallback(acled_f, "acled_reference", [])
                    results["acled_refs"] = acled_refs if isinstance(acled_refs, list) else []
                    yield ("acled_refs", results["acled_refs"])
                else:
                    name = fut_to_name[fut]
                    _, fallback = futures[name]
                    results[name] = _result_or_fallback(fut, name, fallback)
                    yield (name, results[name])

    agent_results = _ner_post_processing(results)
    agent_results = _prefilter_and_summarize(agent_results)
    synthesis = _synthesize(conflict, agent_results)
    final = {
        "conflict": conflict,
        "finint": synthesis.get("finint", {}),
        "sigint": synthesis.get("sigint", {}),
        "news": synthesis.get("news", {}),
        "geoint": synthesis.get("geoint", {}),
        "socmint": synthesis.get("socmint", {}),
        "techint": synthesis.get("techint", {}),
        "cyber": synthesis.get("cyber", {}),
        "energy": synthesis.get("energy", {}),
        "protest": synthesis.get("protest", {}),
        "diplo": synthesis.get("diplo", {}),
        "proximity": synthesis.get("proximity", {}),
        "narrative": synthesis.get("narrative", {}),
        "chokepoint": synthesis.get("chokepoint", {}),
        "escalation_score": synthesis.get("escalation_score", 0.0),
        "threat_level": synthesis.get("threat_level", "MINIMAL"),
        "key_findings": synthesis.get("key_findings", []),
        "scenarios": synthesis.get("scenarios", []),
        "summary": synthesis.get("summary", ""),
        "actors": synthesis.get("actors", []),
        "predictive": synthesis.get("predictive", {}),
        "compliance": synthesis.get("compliance", {}),
        "alerts": synthesis.get("alerts", []),
    }
    yield ("supervisor", final)


def _agents_seem_contradictory(scores: List[float]) -> bool:
    if len(scores) < 2:
        return False
    threshold = float(os.getenv("SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD", "50"))
    return (max(scores) - min(scores)) >= threshold


_SUPERVISOR_SYSTEM_PROMPT = """You are a senior intelligence analyst with access to 10 intelligence streams:
- FININT: Financial markets and oil price indicators
- SIGINT: Military aircraft, naval vessels, and conflict intel (BBC, DW, Al Jazeera, RFE/RL, think tanks)
- NEWS: Open-source media sentiment analysis
- GEOINT: Satellite thermal anomaly detection
- SOCMINT: Social media signals from Telegram, Reddit, and RSS
- TECHINT: Tech sector indicators, export control news, IODA internet outage events (escalation signal)
- CYBER: CISA KEV, threat intel reports, OTX pulses (APT/exploit indicators)
- ENERGY: EU gas storage (AGSI+), commodity prices (Brent, WTI), food commodities (Wheat, Corn, Soy), FAO Food Price Index, fertilizer prices (Urea, DAP), food security risk
- PROTEST: ACLED protests/riots, GDELT protest coverage (civil society unrest)
- DIPLO: OFAC/EU sanctions, UN/ICJ press (diplomatic/legal signals)
- PROXIMITY: Strike–civilian correlation (NASA FIRMS + OSM schools/hospitals, human-shield / collateral risk)
- CHOKEPOINT: Maritime chokepoint monitoring (Strait of Hormuz, Bab el-Mandeb, Suez Canal) – tanker density, oil flow estimates, disruption risk scoring, data quality transparency

When the payload includes "narrative", this is the Signal Framework: state vs exile/independent media comparison (e.g. IRNA/Fars vs Iran International/Radio Farda). Use synthesis_text, synthesis_probability, and source_comparison_table to inform key_findings and summary when relevant (e.g. information vacuum, framing divergence).

When the payload includes "acled_reference_analyses", these are curated ACLED analysis pages (Middle East / Iran updates, expert comments, reports) whose content has been fetched and extracted. Use these analyses to inform key_findings, scenarios, and summary—e.g. ACLED assessments on Kurdish dynamics, Hezbollah, Gulf states, ground invasion risks—not as mere links but as substantive context. For conflict Iran/Middle East, include Hezbollah–IDF and Houthi dynamics in key_findings and summary when the agent data supports it. For conflict Iran/Middle East, explicitly address global impacts in key_findings and summary when data supports it: oil price moves (Brent/WTI), Strait of Hormuz / chokepoint risk, EU gas storage, and supply chain implications.

Agent results may be produced by rule-based tool chains (fixed tool order, no per-agent LLM). Treat the payload as authoritative: use the composite_score and per-stream scores, and derive key_findings, scenarios, and summary from the raw data (articles, aircraft, anomalies, signals, sanctions, protests, etc.) and the stream summaries provided. Your output format and quality standards are unchanged.

Analyze all streams holistically and return ONLY valid JSON with no markdown:
{
  "escalation_score": <number 0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise finding strings>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF summary>"
}"""


_MAX_PAYLOAD_CHARS = 250_000


def _compact_for_llm(agent_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only what the supervisor LLM needs: score, summary, and compact top items.
    Narrative (Signal Framework) returns here; all code below is for other agents only.
    """
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
    for key in ("articles", "top_signals", "conflict_reports", "threat_reports",
                "protest_articles", "un_icj_news", "evidence", "hotspots",
                "tech_indicators", "export_controls", "ioda_events",
                "protest_events", "commodities", "otx_pulses"):
        items = result.get(key)
        if isinstance(items, list) and items:
            compact = []
            for item in items[:3]:
                if isinstance(item, dict):
                    compact.append({k: (str(v)[:120] if isinstance(v, str) and len(v) > 120 else v) for k, v in list(item.items())[:6]})
                elif isinstance(item, str):
                    compact.append(item[:150])
                else:
                    compact.append(item)
            out[key] = compact
    for key in ("aircraft", "ships"):
        items = result.get(key)
        if isinstance(items, list):
            out[f"{key}_count"] = len([i for i in items if isinstance(i, dict) and "error" not in i])
    for key in ("brent", "polymarket", "cisa_kev", "ofac_sdn", "eu_sanctions",
                "agsi_storage", "greynoise_scan_context",
                "food_commodities", "fao_fpi", "fertilizer", "food_security_risk"):
        val = result.get(key)
        if val is not None:
            s = json.dumps(val, default=str)
            if len(s) < 500:
                out[key] = val
    if agent_name == "chokepoint":
        out["chokepoints"] = (result.get("chokepoints") or [])[:5]
        out["chokepoint_score"] = result.get("chokepoint_score", 0.0)
    return out


def _rule_based_fallback(combined_score: float) -> Dict[str, Any]:
    if combined_score >= 80: tl = "CRITICAL"
    elif combined_score >= 60: tl = "HIGH"
    elif combined_score >= 40: tl = "ELEVATED"
    elif combined_score >= 20: tl = "LOW"
    else: tl = "MINIMAL"
    return {"escalation_score": combined_score, "threat_level": tl, "key_findings": [], "scenarios": [], "summary": f"Composite {combined_score:.0f}/100. Agent findings below."}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
def _call_supervisor_llm_with_retry(*, user_json: str, model: str) -> str:
    """Call supervisor LLM with retries for transient failures (rate limit, network)."""
    return call_llm(
        system=_SUPERVISOR_SYSTEM_PROMPT,
        user_content=user_json,
        model=model,
        temperature=0.1,
    )


def _synthesize(conflict: str, agent_results: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesize all agent results into a single assessment."""
    acled_refs       = agent_results.get("acled_refs") or []
    finint_result     = agent_results.get("finint") or {}
    sigint_result     = agent_results.get("sigint") or {}
    news_result       = agent_results.get("news") or {}
    geoint_result     = agent_results.get("geoint") or {}
    socmint_result    = agent_results.get("socmint") or {}
    techint_result    = agent_results.get("techint") or {}
    cyber_result      = agent_results.get("cyber") or {}
    energy_result     = agent_results.get("energy") or {}
    protest_result    = agent_results.get("protest") or {}
    diplo_result      = agent_results.get("diplo") or {}
    proximity_result  = agent_results.get("proximity") or {}
    narrative_result  = agent_results.get("narrative") or {}
    chokepoint_result = agent_results.get("chokepoint") or {}

    finint_score     = float(finint_result.get("escalation_score", 0.0))
    sigint_score     = float(sigint_result.get("sigint_score", 0.0))
    news_score       = float(news_result.get("news_score", 0.0))
    geoint_score     = float(geoint_result.get("geoint_score", 0.0))
    socmint_score    = float(socmint_result.get("socmint_score", 0.0))
    techint_score    = float(techint_result.get("techint_score", 0.0))
    cyber_score      = float(cyber_result.get("cyber_score", 0.0))
    energy_score     = float(energy_result.get("energy_score", 0.0))
    protest_score    = float(protest_result.get("protest_score", 0.0))
    diplo_score      = float(diplo_result.get("diplo_score", 0.0))
    proximity_score  = float(proximity_result.get("proximity_score", 0.0))
    chokepoint_score = float(chokepoint_result.get("chokepoint_score", 0.0))

    combined_score = (
        finint_score    * 0.09 +
        sigint_score    * 0.12 +
        news_score      * 0.09 +
        geoint_score    * 0.07 +
        socmint_score   * 0.09 +
        techint_score   * 0.07 +
        cyber_score     * 0.07 +
        energy_score    * 0.07 +
        protest_score   * 0.07 +
        diplo_score     * 0.06 +
        proximity_score * 0.09 +
        chokepoint_score * 0.11
    )

    agent_scores_for_predictive = {
        "finint": finint_score,
        "sigint": sigint_score,
        "news": news_score,
        "geoint": geoint_score,
        "socmint": socmint_score,
        "techint": techint_score,
        "cyber": cyber_score,
        "energy": energy_score,
        "protest": protest_score,
        "diplo": diplo_score,
        "proximity": proximity_score,
        "chokepoint": chokepoint_score,
    }

    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    if use_rule_based:
        parsed = _rule_based_fallback(combined_score)
    else:
        require_api_key()
        use_fallback = os.getenv("USE_SUPERVISOR_FALLBACK_MODEL", "false").strip().lower() in ("1", "true", "yes")
        agent_scores_list = [finint_score, sigint_score, news_score, geoint_score, socmint_score, techint_score, cyber_score, energy_score, protest_score, diplo_score, proximity_score]
        complex_case = use_fallback and _agents_seem_contradictory(agent_scores_list)
        if complex_case:
            model = get_model_name("supervisor_fallback")
        else:
            model = get_model_name("supervisor_routine")

        user_payload = {
            "conflict": conflict,
            "composite_score": combined_score,
            "acled_reference_analyses": [{"url": r.get("url"), "title": r.get("title"), "excerpt": (r.get("excerpt") or "")[:1000]} for r in acled_refs[:3] if isinstance(r, dict) and (r.get("excerpt") or r.get("title"))],
            "agent_scores": {
                "finint": finint_score, "sigint": sigint_score, "news": news_score,
                "geoint": geoint_score, "socmint": socmint_score, "techint": techint_score,
                "cyber": cyber_score, "energy": energy_score, "protest": protest_score,
                "diplo": diplo_score, "proximity": proximity_score,
            },
            "finint": _compact_for_llm("finint", finint_result),
            "sigint": _compact_for_llm("sigint", sigint_result),
            "news": _compact_for_llm("news", news_result),
            "geoint": _compact_for_llm("geoint", geoint_result),
            "socmint": _compact_for_llm("socmint", socmint_result),
            "techint": _compact_for_llm("techint", techint_result),
            "cyber": _compact_for_llm("cyber", cyber_result),
            "energy": _compact_for_llm("energy", energy_result),
            "protest": _compact_for_llm("protest", protest_result),
            "diplo": _compact_for_llm("diplo", diplo_result),
            "proximity": _compact_for_llm("proximity", proximity_result),
            "narrative": _compact_for_llm("narrative", narrative_result),
        }

        user_json = json.dumps(user_payload, default=str)
        if len(user_json) > _MAX_PAYLOAD_CHARS:
            print(f"[supervisor] payload {len(user_json):,} chars > limit, truncating")
            user_json = user_json[:_MAX_PAYLOAD_CHARS]

        try:
            with traced("analysis.supervisor.llm", {"model": model, "conflict": conflict}):
                raw = _call_supervisor_llm_with_retry(
                    user_json=user_json,
                    model=model,
                )
        except Exception as llm_err:
            _logger.warning("Supervisor LLM failed after retries: %s - rule-based fallback", llm_err)
            raw = None

        if raw is None:
            parsed = _rule_based_fallback(combined_score)
        else:
            raw = raw.strip()
            if "```" in raw:
                m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                if m:
                    raw = m.group(1).strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = _rule_based_fallback(combined_score)

    threat_level = str(parsed.get("threat_level", "MINIMAL"))
    key_findings = list(parsed.get("key_findings") or [])
    scenarios    = list(parsed.get("scenarios") or [])
    summary      = str(parsed.get("summary", ""))

    key_findings = append_agent_findings(key_findings, agent_results, conflict, chokepoint_score)
    actors = build_actors_for_conflict(conflict, key_findings)

    # ── Predictive block (baseline + simple 24h forecast) ─────────────────────────
    predictive = build_predictive_block(conflict, combined_score, agent_scores_for_predictive)

    # ── Chokepoint enrichment (cross-reference with other agents) ───────────
    chokepoint_enriched = enrich_chokepoints(
        chokepoint_data=chokepoint_result,
        sigint_data=sigint_result,
        energy_data=energy_result,
        news_data=news_result,
        diplo_data=diplo_result,
    )
    agent_results["chokepoint"] = chokepoint_enriched

    sigint_data = agent_results.get("sigint") or {}
    compliance, alerts, upd_prev_sigint, upd_prev_ts = build_compliance_and_alerts(
        sigint_data,
        conflict,
        threat_level,
        diplo_result,
        agent_results,
        _previous_sigint.get(conflict),
        _previous_sigint_ts.get(conflict),
    )
    if sigint_data.get("ships"):
        _previous_sigint[conflict] = upd_prev_sigint
        _previous_sigint_ts[conflict] = upd_prev_ts

    return {
        "escalation_score": combined_score,
        "threat_level": threat_level,
        "key_findings": key_findings,
        "scenarios": scenarios,
        "summary": summary,
        "actors": actors,
        "predictive": predictive,
        "compliance": compliance,
        "alerts": alerts,
        **{k: v for k, v in agent_results.items() if k != "acled_refs"},
    }


def _ner_post_processing(agent_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-processing: extract NER entities from NEWS and SOCMINT, then enrich
    FININT (OFAC cross-ref) and GEOINT (location correlation).
    Operates in-place on agent_results.
    """
    news_entities = agent_results.get("news", {}).get("entities", [])
    socmint_entities = agent_results.get("socmint", {}).get("entities", [])

    all_entities = news_entities + socmint_entities
    if not all_entities:
        return agent_results

    # Deduplicate by (entity, type)
    seen = set()
    unique_entities: List[Dict[str, Any]] = []
    for ent in all_entities:
        key = (ent.get("entity", "").lower(), ent.get("type", ""))
        if key not in seen and key[0]:
            seen.add(key)
            unique_entities.append(ent)

    if "finint" in agent_results and isinstance(agent_results["finint"], dict):
        agent_results["finint"] = finint_enrich_ner(agent_results["finint"], unique_entities)

    if "geoint" in agent_results and isinstance(agent_results["geoint"], dict):
        agent_results["geoint"] = geoint_enrich_ner(agent_results["geoint"], unique_entities)

    return agent_results


_CLASSIFY_CONFIDENCE_THRESHOLD = float(os.getenv("CLASSIFY_CONFIDENCE_THRESHOLD", "0.3"))
_SUMMARIZE_CHAR_THRESHOLD = int(os.getenv("SUMMARIZE_CHAR_THRESHOLD", "600"))


def _prefilter_and_summarize(agent_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 3 pre-processing before _compact_for_llm / _synthesize:
    1. Zero-shot classification on NEWS articles and SOCMINT signals —
       remove items classified as "other" with low confidence.
    2. Summarize long text items to reduce LLM context consumption.
    Operates in-place on agent_results. Graceful: skips if Haiku unavailable.
    """
    try:
        from services.haiku_service import classify, summarize, is_haiku_failed
    except ImportError:
        return agent_results

    if is_haiku_failed():
        return agent_results

    # 1. Classify + filter NEWS articles
    news = agent_results.get("news", {})
    articles = news.get("articles", [])
    if articles:
        articles = _classify_filter_items(
            articles,
            text_key_primary="title",
            text_key_secondary="summary",
        )
        news["articles"] = articles
        agent_results["news"] = news

    # 2. Classify + filter SOCMINT top_signals (the raw post lists are large;
    #    we only filter the items that flow into _compact_for_llm)
    socmint = agent_results.get("socmint", {})
    for post_key in ("telegram_posts", "twitter_posts", "reddit_posts"):
        posts = socmint.get(post_key, [])
        if posts:
            socmint[post_key] = _classify_filter_items(
                posts,
                text_key_primary="text",
                text_key_secondary="title",
            )
    agent_results["socmint"] = socmint

    # 3. Summarize long texts in articles and posts
    _summarize_long_items(agent_results)

    return agent_results


def _classify_filter_items(
    items: List[Dict[str, Any]],
    text_key_primary: str = "title",
    text_key_secondary: str = "summary",
) -> List[Dict[str, Any]]:
    """Classify items and remove those classified as 'other' with low confidence."""
    if not items or len(items) <= 3:
        return items

    try:
        from services.haiku_service import batch_classify
    except ImportError:
        return items

    texts = [
        ((it.get(text_key_primary) or "") + " " + (it.get(text_key_secondary) or "")).strip()[:500]
        for it in items
    ]
    results = run_async(batch_classify(texts))
    if not results or all(r is None for r in results):
        return items

    filtered = []
    removed = 0
    for item, cls in zip(items, results):
        if cls is None:
            filtered.append(item)
            continue
        item["_classification"] = cls
        if cls.get("category") == "other" and cls.get("confidence", 0) < _CLASSIFY_CONFIDENCE_THRESHOLD:
            removed += 1
            continue
        filtered.append(item)

    if removed:
        _logger.info("[supervisor] Pre-filter removed %d/%d items classified as 'other'", removed, len(items))
    return filtered


def _summarize_long_items(agent_results: Dict[str, Any]):
    """Summarize long text fields in NEWS articles and SOCMINT posts in-place."""
    try:
        from services.haiku_service import summarize
    except ImportError:
        return

    # NEWS articles: summarize long summaries
    for article in agent_results.get("news", {}).get("articles", [])[:10]:
        summary_text = article.get("summary") or ""
        if len(summary_text) > _SUMMARIZE_CHAR_THRESHOLD:
            condensed = run_async(summarize(summary_text))
            if condensed:
                article["summary_original_len"] = len(summary_text)
                article["summary"] = condensed

    # SOCMINT: summarize long post texts
    socmint = agent_results.get("socmint", {})
    for post_key in ("telegram_posts", "twitter_posts", "reddit_posts"):
        for post in socmint.get(post_key, [])[:10]:
            text = post.get("text") or post.get("body_excerpt") or ""
            if len(text) > _SUMMARIZE_CHAR_THRESHOLD:
                condensed = run_async(summarize(text))
                if condensed:
                    post["text_original_len"] = len(text)
                    post["text"] = condensed


def analyze_conflict(conflict: str) -> Dict[str, Any]:
    """Public entrypoint – runs all 11 agents then supervisor synthesis."""
    with traced("analysis.full", {"conflict": conflict}):
        agent_results = _collect_all_agents(conflict)
        agent_results = _ner_post_processing(agent_results)
        agent_results = _prefilter_and_summarize(agent_results)
        synthesis = _synthesize(conflict, agent_results)

    return {
        "conflict": conflict,
        "finint":   synthesis.get("finint", {}),
        "sigint":   synthesis.get("sigint", {}),
        "news":     synthesis.get("news", {}),
        "geoint":   synthesis.get("geoint", {}),
        "socmint":  synthesis.get("socmint", {}),
        "techint":  synthesis.get("techint", {}),
        "cyber":    synthesis.get("cyber", {}),
        "energy":   synthesis.get("energy", {}),
        "protest":  synthesis.get("protest", {}),
        "diplo":    synthesis.get("diplo", {}),
        "proximity": synthesis.get("proximity", {}),
        "narrative": synthesis.get("narrative", {}),
        "chokepoint": synthesis.get("chokepoint", {}),
        "escalation_score": synthesis.get("escalation_score", 0.0),
        "threat_level":     synthesis.get("threat_level", "MINIMAL"),
        "key_findings":     synthesis.get("key_findings", []),
        "scenarios":        synthesis.get("scenarios", []),
        "summary":          synthesis.get("summary", ""),
        "actors":           synthesis.get("actors", []),
        "predictive":       synthesis.get("predictive", {}),
        "compliance":       synthesis.get("compliance", {}),
        "alerts":           synthesis.get("alerts", []),
    }
