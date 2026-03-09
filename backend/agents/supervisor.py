"""
Supervisor – LangGraph Multi-Agent Orchestrator
Coordinates FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT, CYBER, ENERGY, PROTEST, DIPLO agents in parallel,
then runs an LLM (default: Haiku; Sonnet when agent scores disagree) for final assessment.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from .llm_factory import get_supervisor_model, require_supervisor_api_key
from langgraph.graph import END, StateGraph

from .finint_agent import run_finint_agent
from .geoint_agent import run_geoint_agent
from .news_agent import run_news_agent
from .sigint_agent import run_sigint_agent
from .socmint_agent import run_socmint_agent
from .techint_agent import run_techint_agent
from .cyber_agent import run_cyber_agent
from .energy_agent import run_energy_agent
from .protest_agent import run_protest_agent
from .diplo_agent import run_diplo_agent
from .proximity_agent import run_proximity_agent
from .acled_reference import fetch_acled_reference_analyses_sync


# ── State ──────────────────────────────────────────────────────────────────

class AnalysisState(TypedDict, total=False):
    conflict: str
    acled_reference_result: List[Dict[str, Any]]
    finint_result: Dict[str, Any]
    sigint_result: Dict[str, Any]
    news_result: Dict[str, Any]
    geoint_result: Dict[str, Any]
    socmint_result: Dict[str, Any]
    techint_result: Dict[str, Any]
    cyber_result: Dict[str, Any]
    energy_result: Dict[str, Any]
    protest_result: Dict[str, Any]
    diplo_result: Dict[str, Any]
    proximity_result: Dict[str, Any]
    escalation_score: float
    threat_level: str
    key_findings: List[str]
    scenarios: List[Dict[str, Any]]
    summary: str


# ── Intelligence Collection Node (all 10 agents in parallel) ───────────────

# Per-agent timeout (seconds). Prevents one slow API from blocking the whole run.
_AGENT_TIMEOUT = 75


def _result_or_fallback(future, agent_name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Get future.result() with timeout; return fallback on timeout or error."""
    try:
        return future.result(timeout=_AGENT_TIMEOUT)
    except Exception as e:
        return {**fallback, "error": str(e), "timeout_or_error": True}


def collection_node(state: AnalysisState) -> AnalysisState:
    """Run all 10 intelligence agents in parallel with per-agent timeout.
    When USE_RULE_BASED_AGENTS is set, each agent uses its fixed tool chain (no LLM); output shape is unchanged."""
    conflict = state.get("conflict") or ""

    with ThreadPoolExecutor(max_workers=12) as executor:
        finint_f   = executor.submit(run_finint_agent, conflict)
        sigint_f   = executor.submit(run_sigint_agent, conflict)
        news_f     = executor.submit(run_news_agent, conflict)
        geoint_f   = executor.submit(run_geoint_agent, conflict)
        socmint_f  = executor.submit(run_socmint_agent, conflict)
        techint_f  = executor.submit(run_techint_agent, conflict)
        cyber_f    = executor.submit(run_cyber_agent, conflict)
        energy_f   = executor.submit(run_energy_agent, conflict)
        protest_f  = executor.submit(run_protest_agent, conflict)
        diplo_f    = executor.submit(run_diplo_agent, conflict)
        proximity_f = executor.submit(run_proximity_agent, conflict)
        acled_ref_f = executor.submit(fetch_acled_reference_analyses_sync, conflict)

        finint_result   = _result_or_fallback(finint_f, "finint", {"escalation_score": 0.0, "brent": None, "polymarket": []})
        sigint_result   = _result_or_fallback(sigint_f, "sigint", {"sigint_score": 0.0, "aircraft": [], "ships": [], "conflict_reports": []})
        news_result     = _result_or_fallback(news_f, "news", {"news_score": 0.0, "articles": [], "summary": ""})
        geoint_result   = _result_or_fallback(geoint_f, "geoint", {"geoint_score": 0.0, "anomalies": [], "hotspots": []})
        socmint_result  = _result_or_fallback(socmint_f, "socmint", {"socmint_score": 0.0, "top_signals": []})
        techint_result  = _result_or_fallback(techint_f, "techint", {"techint_score": 0.0, "tech_indicators": [], "ioda_events": []})
        cyber_result    = _result_or_fallback(cyber_f, "cyber", {"cyber_score": 0.0, "cisa_kev": {}, "threat_reports": [], "otx_pulses": []})
        energy_result   = _result_or_fallback(energy_f, "energy", {"energy_score": 0.0, "agsi_storage": {}, "commodities": []})
        protest_result  = _result_or_fallback(protest_f, "protest", {"protest_score": 0.0, "protest_events": [], "protest_articles": []})
        diplo_result    = _result_or_fallback(diplo_f, "diplo", {"diplo_score": 0.0, "ofac_sdn": {}, "eu_sanctions": {}, "un_icj_news": []})
        proximity_result = _result_or_fallback(proximity_f, "proximity", {"proximity_score": 0.0, "evidence": [], "summary": ""})
        acled_reference_result = _result_or_fallback(acled_ref_f, "acled_reference", [])

    return {
        "acled_reference_result": acled_reference_result if isinstance(acled_reference_result, list) else [],
        "finint_result":   finint_result,
        "sigint_result":   sigint_result,
        "news_result":     news_result,
        "geoint_result":   geoint_result,
        "socmint_result":  socmint_result,
        "techint_result":  techint_result,
        "cyber_result":    cyber_result,
        "energy_result":   energy_result,
        "protest_result":  protest_result,
        "diplo_result":    diplo_result,
        "proximity_result": proximity_result,
    }


# ── Supervisor Node ───────────────────────────────────────────────────────

def _agents_seem_contradictory(scores: List[float]) -> bool:
    """
    True if agent scores disagree strongly (e.g. one stream high, another low).
    Only used when USE_SUPERVISOR_FALLBACK_MODEL=true; then we use the fallback model (e.g. Sonnet).
    """
    if len(scores) < 2:
        return False
    threshold = float(os.getenv("SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD", "50"))
    score_range = max(scores) - min(scores)
    return score_range >= threshold


def supervisor_node(state: AnalysisState) -> AnalysisState:
    """Synthesizes all 11 intelligence streams (Haiku by default; Sonnet when agents disagree)."""
    conflict        = state.get("conflict") or ""
    acled_refs      = state.get("acled_reference_result") or []
    if not isinstance(acled_refs, list):
        acled_refs = []
    finint_result   = state.get("finint_result") or {}
    sigint_result   = state.get("sigint_result") or {}
    news_result     = state.get("news_result") or {}
    geoint_result   = state.get("geoint_result") or {}
    socmint_result  = state.get("socmint_result") or {}
    techint_result  = state.get("techint_result") or {}
    cyber_result    = state.get("cyber_result") or {}
    energy_result   = state.get("energy_result") or {}
    protest_result  = state.get("protest_result") or {}
    diplo_result    = state.get("diplo_result") or {}
    proximity_result = state.get("proximity_result") or {}

    # Extract scores
    finint_score   = float(finint_result.get("escalation_score", 0.0))
    sigint_score   = float(sigint_result.get("sigint_score", 0.0))
    news_score     = float(news_result.get("news_score", 0.0))
    geoint_score   = float(geoint_result.get("geoint_score", 0.0))
    socmint_score  = float(socmint_result.get("socmint_score", 0.0))
    techint_score  = float(techint_result.get("techint_score", 0.0))
    cyber_score    = float(cyber_result.get("cyber_score", 0.0))
    energy_score   = float(energy_result.get("energy_score", 0.0))
    protest_score  = float(protest_result.get("protest_score", 0.0))
    diplo_score    = float(diplo_result.get("diplo_score", 0.0))
    proximity_score = float(proximity_result.get("proximity_score", 0.0))

    # Weighted composite score (11 agents: FININT … DIPLO + PROXIMITY)
    # Weights sum to 1.0; PROXIMITY 8%, rest scaled proportionally
    combined_score = (
        finint_score   * 0.10 +
        sigint_score   * 0.13 +
        news_score     * 0.10 +
        geoint_score   * 0.08 +
        socmint_score  * 0.10 +
        techint_score  * 0.08 +
        cyber_score    * 0.08 +
        energy_score   * 0.08 +
        protest_score  * 0.08 +
        diplo_score    * 0.07 +
        proximity_score * 0.10
    )

    require_supervisor_api_key()

    # Regelbasiert = kein LLM-Aufruf (günstig); sonst LLM für Synthese
    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    if use_rule_based:
        # Ohne LLM: Score aus Gewichtung, Threat aus Schwellen, Summary kurz aus Scores
        if combined_score >= 80:
            threat_level = "CRITICAL"
        elif combined_score >= 60:
            threat_level = "HIGH"
        elif combined_score >= 40:
            threat_level = "ELEVATED"
        elif combined_score >= 20:
            threat_level = "LOW"
        else:
            threat_level = "MINIMAL"
        parsed = {
            "escalation_score": combined_score,
            "threat_level": threat_level,
            "key_findings": [],
            "scenarios": [],
            "summary": f"Composite {combined_score:.0f}/100 (FININT {finint_score:.0f}, SIGINT {sigint_score:.0f}, NEWS {news_score:.0f}, GEOINT {geoint_score:.0f}, SOCMINT {socmint_score:.0f}, TECHINT {techint_score:.0f}, CYBER {cyber_score:.0f}, ENERGY {energy_score:.0f}, PROTEST {protest_score:.0f}, DIPLO {diplo_score:.0f}, PROXIMITY {proximity_score:.0f}). Key findings below from agents.",
        }
    else:
        # Mit LLM: Haiku standardmäßig; bei Widerspruch optional Sonnet (USE_SUPERVISOR_FALLBACK_MODEL=true).
        # Default: Fallback aus → immer Haiku. Schwellwert: SUPERVISOR_CONTRADICTION_RANGE_THRESHOLD (default 50).
        use_fallback = os.getenv("USE_SUPERVISOR_FALLBACK_MODEL", "false").strip().lower() in ("1", "true", "yes")
        agent_scores_list = [finint_score, sigint_score, news_score, geoint_score, socmint_score, techint_score, cyber_score, energy_score, protest_score, diplo_score, proximity_score]
        complex_case = use_fallback and _agents_seem_contradictory(agent_scores_list)
        model = get_supervisor_model(complex_case=complex_case)
        system_prompt = """You are a senior intelligence analyst with access to 10 intelligence streams:
- FININT: Financial markets and oil price indicators
- SIGINT: Military aircraft, naval vessels, and conflict intel (BBC, DW, Al Jazeera, RFE/RL, think tanks)
- NEWS: Open-source media sentiment analysis
- GEOINT: Satellite thermal anomaly detection
- SOCMINT: Social media signals from Telegram, Reddit, and RSS
- TECHINT: Tech sector indicators, export control news, IODA internet outage events (escalation signal)
- CYBER: CISA KEV, threat intel reports, OTX pulses (APT/exploit indicators)
- ENERGY: EU gas storage (AGSI+), commodity prices (Brent, WTI)
- PROTEST: ACLED protests/riots, GDELT protest coverage (civil society unrest)
- DIPLO: OFAC/EU sanctions, UN/ICJ press (diplomatic/legal signals)
- PROXIMITY: Strike–civilian correlation (NASA FIRMS + OSM schools/hospitals, human-shield / collateral risk)

When the payload includes "acled_reference_analyses", these are curated ACLED analysis pages (Middle East / Iran updates, expert comments, reports) whose content has been fetched and extracted. Use these analyses to inform key_findings, scenarios, and summary—e.g. ACLED assessments on Kurdish dynamics, Hezbollah, Gulf states, ground invasion risks—not as mere links but as substantive context.

Agent results may be produced by rule-based tool chains (fixed tool order, no per-agent LLM). Treat the payload as authoritative: use the composite_score and per-stream scores, and derive key_findings, scenarios, and summary from the raw data (articles, aircraft, anomalies, signals, sanctions, protests, etc.) and the stream summaries provided. Your output format and quality standards are unchanged.

Analyze all streams holistically and return ONLY valid JSON with no markdown:
{
  "escalation_score": <number 0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise finding strings>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF summary>"
}"""
        user_payload = {
            "conflict": conflict,
            "composite_score": combined_score,
            "acled_reference_analyses": [{"url": r.get("url"), "title": r.get("title"), "excerpt": (r.get("excerpt") or "")[:2000]} for r in acled_refs if isinstance(r, dict) and (r.get("excerpt") or r.get("title"))],
            "agent_scores": {
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
            },
            "finint": finint_result,
            "sigint": sigint_result,
            "news": news_result,
            "geoint": geoint_result,
            "socmint": socmint_result,
            "techint": techint_result,
            "cyber": cyber_result,
            "energy": energy_result,
            "protest": protest_result,
            "diplo": diplo_result,
            "proximity": proximity_result,
        }
        msg = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(user_payload, default=str)),
        ])
        content = msg.content if hasattr(msg, "content") else str(msg)
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        raw = (content or "").strip()
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if m:
                raw = m.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "escalation_score": combined_score,
                "threat_level": "ELEVATED",
                "key_findings": ["Synthese-Ausgabe konnte nicht gelesen werden; Agent-Daten unten."],
                "scenarios": [],
                "summary": f"Composite score {combined_score:.0f}/100 aus 10 Agenten. Einzelne Streams (News, SIGINT, CYBER, ENERGY, PROTEST, DIPLO, etc.) unten.",
            }

    threat_level = str(parsed.get("threat_level", "MINIMAL"))
    key_findings = list(parsed.get("key_findings") or [])
    scenarios    = list(parsed.get("scenarios") or [])
    summary      = str(parsed.get("summary", ""))

    # Append top news headlines
    for art in (news_result.get("articles") or [])[:3]:
        title  = art.get("title") or "News article"
        source = art.get("source") or "Unknown"
        label  = art.get("sentiment_label") or "NEUTRAL"
        key_findings.append(f"NEWS ({label}) – {title} [{source}]")

    # Append top SOCMINT signals
    for signal in (socmint_result.get("top_signals") or [])[:3]:
        key_findings.append(f"SOCMINT – {signal}")

    # Append SIGINT: aircraft, ships, conflict reports (CriticalThreats, LongWarJournal, etc.)
    ac_list = sigint_result.get("aircraft") or []
    ships_list = sigint_result.get("ships") or []
    for a in ac_list[:2]:
        if isinstance(a, dict) and "error" not in a:
            key_findings.append(f"SIGINT – {a.get('category', 'aircraft')}: {a.get('flight', '?')} ({a.get('region', a.get('source', ''))})")
    if ships_list:
        key_findings.append(f"SIGINT – {len(ships_list)} warship(s) in region")
    for r in (sigint_result.get("conflict_reports") or [])[:3]:
        if isinstance(r, dict) and "error" not in r and r.get("title"):
            key_findings.append(f"SIGINT (intel) – {r.get('title', '')[:70]} [{r.get('source', '')}]")

    # Append GEOINT hotspots
    for h in (geoint_result.get("hotspots") or [])[:2]:
        lat = h.get("lat"); lon = h.get("lon"); frp = h.get("frp")
        anomaly_type = h.get("type") or "anomaly"
        key_findings.append(f"GEOINT ({anomaly_type}) – Thermal anomaly at {lat},{lon} FRP={frp}")

    # Append TECHINT: tech indicators, export control, IODA, OONI, Cloudflare, Shodan
    for ind in (techint_result.get("tech_indicators") or [])[:2]:
        if ind.get("symbol") and "error" not in ind:
            key_findings.append(f"TECHINT – {ind.get('symbol')} {ind.get('change_pct', '')} ({ind.get('label', '')})")
    for art in (techint_result.get("export_controls") or [])[:1]:
        if art.get("title") and "error" not in art:
            key_findings.append(f"TECHINT (export controls) – {art.get('title')} [{art.get('source', '')}]")
    for ev in (techint_result.get("ioda_events") or [])[:2]:
        if isinstance(ev, dict) and "error" not in ev and ev.get("entityCode"):
            key_findings.append(f"TECHINT (IODA) – Internet outage/event in {ev.get('entityCode', '')}")
    if techint_result.get("ooni", {}).get("telegram_signal_blocked_iran"):
        key_findings.append("TECHINT (OONI) – Telegram/Signal confirmed blocked in Iran (escalation)")
    for o in (techint_result.get("cloudflare_outages") or [])[:1]:
        if isinstance(o, dict) and "error" not in o:
            scope = o.get("scope") or ""
            out = o.get("outage") or {}
            cause = out.get("outageCause", "") if isinstance(out, dict) else str(out)
            key_findings.append(f"TECHINT (Cloudflare) – Outage: {scope} {cause}".strip())
    if techint_result.get("shodan", {}).get("total_count"):
        key_findings.append(f"TECHINT (Shodan) – {techint_result['shodan']['total_count']} hosts in conflict region(s)")

    # Append CYBER: CISA KEV, threat reports, OTX
    if cyber_result.get("cisa_kev", {}).get("total"):
        key_findings.append(f"CYBER (CISA KEV) – {cyber_result['cisa_kev']['total']} known exploited vulnerabilities")
    for r in (cyber_result.get("threat_reports") or [])[:2]:
        if isinstance(r, dict) and r.get("title") and "error" not in r:
            key_findings.append(f"CYBER – {r.get('title', '')[:60]}")

    # Append ENERGY: AGSI storage, commodities
    agsi_full = energy_result.get("agsi_storage", {}).get("full") or []
    if agsi_full:
        avg = sum(float(x.get("full_pct") or 0) for x in agsi_full) / max(len(agsi_full), 1)
        key_findings.append(f"ENERGY (AGSI+) – {len(agsi_full)} storage record(s), avg fill {avg:.0f}%")
    for c in (energy_result.get("commodities") or [])[:2]:
        if c.get("symbol") and "error" not in c and c.get("price"):
            key_findings.append(f"ENERGY – {c.get('symbol')} {c.get('price')} ({c.get('change_pct', '')})")

    # Append PROTEST: ACLED events, GDELT articles
    protest_events = protest_result.get("protest_events") or []
    valid_pe = [e for e in protest_events if isinstance(e, dict) and "error" not in e]
    if valid_pe:
        key_findings.append(f"PROTEST (ACLED) – {len(valid_pe)} protest/riot events")
    for a in (protest_result.get("protest_articles") or [])[:1]:
        if isinstance(a, dict) and a.get("title") and "error" not in a:
            key_findings.append(f"PROTEST (GDELT) – {a.get('title', '')[:55]}")

    # Append DIPLO: OFAC, EU, UN/ICJ
    ofac_matches = diplo_result.get("ofac_sdn", {}).get("total_matches") or 0
    if ofac_matches:
        key_findings.append(f"DIPLO (OFAC SDN) – {ofac_matches} conflict-relevant entries")
    for n in (diplo_result.get("un_icj_news") or [])[:2]:
        if isinstance(n, dict) and n.get("title") and "error" not in n:
            key_findings.append(f"DIPLO ({n.get('source', 'UN/ICJ')}) – {n.get('title', '')[:55]}")

    # PROXIMITY: strike–civilian / human-shield evidence
    for ev in (proximity_result.get("evidence") or [])[:3]:
        if isinstance(ev, dict) and ev.get("summary"):
            risk = ev.get("riskLabel", "")
            key_findings.append(f"PROXIMITY ({risk}) – {ev.get('summary', '')[:75]}")

    # ACLED reference analyses (curated Middle East / Iran pages – context for synthesis)
    for ref in acled_refs[:3]:
        if isinstance(ref, dict) and ref.get("title") and "error" not in str(ref.get("excerpt", ""))[:50]:
            key_findings.append(f"ACLED reference – {ref.get('title', '')[:70]}")

    return {
        "escalation_score": combined_score,
        "threat_level": threat_level,
        "key_findings": key_findings,
        "scenarios": scenarios,
        "summary": summary,
    }


# ── Graph ──────────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("collection", collection_node)
    graph.add_node("supervisor", supervisor_node)
    graph.set_entry_point("collection")
    graph.add_edge("collection", "supervisor")
    graph.add_edge("supervisor", END)
    return graph.compile()


_COMPILED_GRAPH = build_graph()


def analyze_conflict(conflict: str) -> Dict[str, Any]:
    """Public entrypoint – runs all 10 agents then supervisor synthesis."""
    result = _COMPILED_GRAPH.invoke({"conflict": conflict})
    return {
        "conflict": conflict,
        "finint":   result.get("finint_result", {}),
        "sigint":   result.get("sigint_result", {}),
        "news":     result.get("news_result", {}),
        "geoint":   result.get("geoint_result", {}),
        "socmint":  result.get("socmint_result", {}),
        "techint":  result.get("techint_result", {}),
        "cyber":    result.get("cyber_result", {}),
        "energy":   result.get("energy_result", {}),
        "protest":  result.get("protest_result", {}),
        "diplo":    result.get("diplo_result", {}),
        "proximity": result.get("proximity_result", {}),
        "escalation_score": result.get("escalation_score", 0.0),
        "threat_level":     result.get("threat_level", "MINIMAL"),
        "key_findings":     result.get("key_findings", []),
        "scenarios":        result.get("scenarios", []),
        "summary":          result.get("summary", ""),
    }
