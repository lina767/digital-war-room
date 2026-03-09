"""
Supervisor – Multi-Agent Orchestrator (no frameworks).
Coordinates 11 agents in parallel, then runs an LLM for final assessment.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from .llm import call_llm, get_model_name, require_api_key
from .otel_callbacks import traced

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


# Per-agent timeout (seconds). Prevents one slow API from blocking the whole run.
_AGENT_TIMEOUT = 75


def _result_or_fallback(future, agent_name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return future.result(timeout=_AGENT_TIMEOUT)
    except Exception as e:
        return {**fallback, "error": str(e), "timeout_or_error": True}


def _collect_all_agents(conflict: str) -> Dict[str, Any]:
    """Run all 11 intelligence agents + ACLED reference in parallel."""
    with traced("analysis.collection", {"conflict": conflict}):
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                "finint":   (executor.submit(run_finint_agent, conflict), {"escalation_score": 0.0, "brent": None, "polymarket": []}),
                "sigint":   (executor.submit(run_sigint_agent, conflict), {"sigint_score": 0.0, "aircraft": [], "ships": [], "conflict_reports": []}),
                "news":     (executor.submit(run_news_agent, conflict), {"news_score": 0.0, "articles": [], "summary": ""}),
                "geoint":   (executor.submit(run_geoint_agent, conflict), {"geoint_score": 0.0, "anomalies": [], "hotspots": []}),
                "socmint":  (executor.submit(run_socmint_agent, conflict), {"socmint_score": 0.0, "top_signals": []}),
                "techint":  (executor.submit(run_techint_agent, conflict), {"techint_score": 0.0, "tech_indicators": [], "ioda_events": [], "ioda_outages": [], "ioda_alerts": [], "ioda_signals_raw": [], "ioda_entities": []}),
                "cyber":    (executor.submit(run_cyber_agent, conflict), {"cyber_score": 0.0, "cisa_kev": {}, "threat_reports": [], "otx_pulses": [], "greynoise_scan_context": {}}),
                "energy":   (executor.submit(run_energy_agent, conflict), {"energy_score": 0.0, "agsi_storage": {}, "commodities": []}),
                "protest":  (executor.submit(run_protest_agent, conflict), {"protest_score": 0.0, "protest_events": [], "protest_articles": []}),
                "diplo":    (executor.submit(run_diplo_agent, conflict), {"diplo_score": 0.0, "ofac_sdn": {}, "eu_sanctions": {}, "un_icj_news": []}),
                "proximity":(executor.submit(run_proximity_agent, conflict), {"proximity_score": 0.0, "evidence": [], "summary": ""}),
            }
            acled_ref_f = executor.submit(fetch_acled_reference_analyses_sync, conflict)

            results = {}
            for name, (fut, fallback) in futures.items():
                results[name] = _result_or_fallback(fut, name, fallback)
            acled_refs = _result_or_fallback(acled_ref_f, "acled_reference", [])
            results["acled_refs"] = acled_refs if isinstance(acled_refs, list) else []

    return results


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
- ENERGY: EU gas storage (AGSI+), commodity prices (Brent, WTI)
- PROTEST: ACLED protests/riots, GDELT protest coverage (civil society unrest)
- DIPLO: OFAC/EU sanctions, UN/ICJ press (diplomatic/legal signals)
- PROXIMITY: Strike–civilian correlation (NASA FIRMS + OSM schools/hospitals, human-shield / collateral risk)

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


def _synthesize(conflict: str, agent_results: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesize all agent results into a single assessment."""
    acled_refs       = agent_results.get("acled_refs") or []
    finint_result    = agent_results.get("finint") or {}
    sigint_result    = agent_results.get("sigint") or {}
    news_result      = agent_results.get("news") or {}
    geoint_result    = agent_results.get("geoint") or {}
    socmint_result   = agent_results.get("socmint") or {}
    techint_result   = agent_results.get("techint") or {}
    cyber_result     = agent_results.get("cyber") or {}
    energy_result    = agent_results.get("energy") or {}
    protest_result   = agent_results.get("protest") or {}
    diplo_result     = agent_results.get("diplo") or {}
    proximity_result = agent_results.get("proximity") or {}

    finint_score    = float(finint_result.get("escalation_score", 0.0))
    sigint_score    = float(sigint_result.get("sigint_score", 0.0))
    news_score      = float(news_result.get("news_score", 0.0))
    geoint_score    = float(geoint_result.get("geoint_score", 0.0))
    socmint_score   = float(socmint_result.get("socmint_score", 0.0))
    techint_score   = float(techint_result.get("techint_score", 0.0))
    cyber_score     = float(cyber_result.get("cyber_score", 0.0))
    energy_score    = float(energy_result.get("energy_score", 0.0))
    protest_score   = float(protest_result.get("protest_score", 0.0))
    diplo_score     = float(diplo_result.get("diplo_score", 0.0))
    proximity_score = float(proximity_result.get("proximity_score", 0.0))

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

    require_api_key()

    use_rule_based = os.getenv("USE_RULE_BASED_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")

    if use_rule_based:
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
        use_fallback = os.getenv("USE_SUPERVISOR_FALLBACK_MODEL", "false").strip().lower() in ("1", "true", "yes")
        agent_scores_list = [finint_score, sigint_score, news_score, geoint_score, socmint_score, techint_score, cyber_score, energy_score, protest_score, diplo_score, proximity_score]
        complex_case = use_fallback and _agents_seem_contradictory(agent_scores_list)
        model = get_model_name("supervisor_fallback" if complex_case else "supervisor")

        user_payload = {
            "conflict": conflict,
            "composite_score": combined_score,
            "acled_reference_analyses": [{"url": r.get("url"), "title": r.get("title"), "excerpt": (r.get("excerpt") or "")[:2000]} for r in acled_refs if isinstance(r, dict) and (r.get("excerpt") or r.get("title"))],
            "agent_scores": {
                "finint": finint_score, "sigint": sigint_score, "news": news_score,
                "geoint": geoint_score, "socmint": socmint_score, "techint": techint_score,
                "cyber": cyber_score, "energy": energy_score, "protest": protest_score,
                "diplo": diplo_score, "proximity": proximity_score,
            },
            "finint": finint_result, "sigint": sigint_result, "news": news_result,
            "geoint": geoint_result, "socmint": socmint_result, "techint": techint_result,
            "cyber": cyber_result, "energy": energy_result, "protest": protest_result,
            "diplo": diplo_result, "proximity": proximity_result,
        }

        with traced("analysis.supervisor.llm", {"model": model, "conflict": conflict}):
            raw = call_llm(
                system=_SUPERVISOR_SYSTEM_PROMPT,
                user_content=json.dumps(user_payload, default=str),
                model=model,
                temperature=0.1,
            )

        raw = raw.strip()
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

    # ── Append agent-level key findings ───────────────────────────────────

    for art in (news_result.get("articles") or [])[:3]:
        title  = art.get("title") or "News article"
        source = art.get("source") or "Unknown"
        label  = art.get("sentiment_label") or "NEUTRAL"
        key_findings.append(f"NEWS ({label}) – {title} [{source}]")

    for signal in (socmint_result.get("top_signals") or [])[:3]:
        key_findings.append(f"SOCMINT – {signal}")

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

    for h in (geoint_result.get("hotspots") or [])[:2]:
        lat = h.get("lat"); lon = h.get("lon"); frp = h.get("frp")
        anomaly_type = h.get("type") or "anomaly"
        key_findings.append(f"GEOINT ({anomaly_type}) – Thermal anomaly at {lat},{lon} FRP={frp}")

    for ind in (techint_result.get("tech_indicators") or [])[:2]:
        if ind.get("symbol") and "error" not in ind:
            key_findings.append(f"TECHINT – {ind.get('symbol')} {ind.get('change_pct', '')} ({ind.get('label', '')})")
    for art in (techint_result.get("export_controls") or [])[:1]:
        if art.get("title") and "error" not in art:
            key_findings.append(f"TECHINT (export controls) – {art.get('title')} [{art.get('source', '')}]")
    for ev in (techint_result.get("ioda_events") or [])[:2]:
        if isinstance(ev, dict) and "error" not in ev and ev.get("entityCode"):
            key_findings.append(f"TECHINT (IODA) – Internet outage/event in {ev.get('entityCode', '')}")
    ioda_outages = [o for o in (techint_result.get("ioda_outages") or []) if isinstance(o, dict) and "error" not in o]
    ioda_alerts = [a for a in (techint_result.get("ioda_alerts") or []) if isinstance(a, dict) and "error" not in a]
    if ioda_outages or ioda_alerts:
        key_findings.append(f"TECHINT (IODA v2) – {len(ioda_outages)} outage(s), {len(ioda_alerts)} BGP/anomaly alert(s); signals (BGP/Ping/Telescope) available.")
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

    if cyber_result.get("cisa_kev", {}).get("total"):
        key_findings.append(f"CYBER (CISA KEV) – {cyber_result['cisa_kev']['total']} known exploited vulnerabilities")
    for r in (cyber_result.get("threat_reports") or [])[:2]:
        if isinstance(r, dict) and r.get("title") and "error" not in r:
            key_findings.append(f"CYBER – {r.get('title', '')[:60]}")
    gn = cyber_result.get("greynoise_scan_context") or {}
    if gn.get("available") and int(gn.get("count") or 0) > 0:
        key_findings.append(f"CYBER (GreyNoise) – {gn['count']} malicious scanners (7d); top actors/countries in context")

    agsi_full = energy_result.get("agsi_storage", {}).get("full") or []
    if agsi_full:
        avg = sum(float(x.get("full_pct") or 0) for x in agsi_full) / max(len(agsi_full), 1)
        key_findings.append(f"ENERGY (AGSI+) – {len(agsi_full)} storage record(s), avg fill {avg:.0f}%")
    for c in (energy_result.get("commodities") or [])[:2]:
        if c.get("symbol") and "error" not in c and c.get("price"):
            key_findings.append(f"ENERGY – {c.get('symbol')} {c.get('price')} ({c.get('change_pct', '')})")
    if conflict and "iran" in conflict.lower():
        note = energy_result.get("global_impact_note")
        if note:
            key_findings.append(f"Global impact – {note}")
        else:
            commodities = energy_result.get("commodities") or []
            valid_c = [c for c in commodities if isinstance(c, dict) and c.get("change_pct_raw") is not None and "error" not in c]
            max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
            if max_up is not None and max_up >= 2.0:
                key_findings.append(f"Global impact – Oil (Brent/WTI) {max_up:+.1f}% – potential Strait of Hormuz / chokepoint risk premium")
    if conflict and "iran" in conflict.lower():
        global_kw = ("hormuz", "hormus", "oil", "chokepoint", "strait")
        for art in (news_result.get("articles") or []):
            if not isinstance(art, dict) or "error" in art:
                continue
            title = (art.get("title") or "").lower()
            if any(kw in title for kw in global_kw):
                src = art.get("source") or "News"
                key_findings.append(f"Global impact (News) – {art.get('title', '')[:70]} [{src}]")
                break

    protest_events = protest_result.get("protest_events") or []
    valid_pe = [e for e in protest_events if isinstance(e, dict) and "error" not in e]
    if valid_pe:
        key_findings.append(f"PROTEST (ACLED) – {len(valid_pe)} protest/riot events")
    for a in (protest_result.get("protest_articles") or [])[:1]:
        if isinstance(a, dict) and a.get("title") and "error" not in a:
            key_findings.append(f"PROTEST (GDELT) – {a.get('title', '')[:55]}")

    ofac_matches = diplo_result.get("ofac_sdn", {}).get("total_matches") or 0
    if ofac_matches:
        key_findings.append(f"DIPLO (OFAC SDN) – {ofac_matches} conflict-relevant entries")
    for n in (diplo_result.get("un_icj_news") or [])[:2]:
        if isinstance(n, dict) and n.get("title") and "error" not in n:
            key_findings.append(f"DIPLO ({n.get('source', 'UN/ICJ')}) – {n.get('title', '')[:55]}")

    for ev in (proximity_result.get("evidence") or [])[:3]:
        if isinstance(ev, dict) and ev.get("summary"):
            risk = ev.get("riskLabel", "")
            key_findings.append(f"PROXIMITY ({risk}) – {ev.get('summary', '')[:75]}")

    for ref in acled_refs[:3]:
        if isinstance(ref, dict) and ref.get("title") and "error" not in str(ref.get("excerpt", ""))[:50]:
            key_findings.append(f"ACLED reference – {ref.get('title', '')[:70]}")

    return {
        "escalation_score": combined_score,
        "threat_level": threat_level,
        "key_findings": key_findings,
        "scenarios": scenarios,
        "summary": summary,
        **{k: v for k, v in agent_results.items() if k != "acled_refs"},
    }


def analyze_conflict(conflict: str) -> Dict[str, Any]:
    """Public entrypoint – runs all 11 agents then supervisor synthesis."""
    with traced("analysis.full", {"conflict": conflict}):
        agent_results = _collect_all_agents(conflict)
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
        "escalation_score": synthesis.get("escalation_score", 0.0),
        "threat_level":     synthesis.get("threat_level", "MINIMAL"),
        "key_findings":     synthesis.get("key_findings", []),
        "scenarios":        synthesis.get("scenarios", []),
        "summary":          synthesis.get("summary", ""),
    }
