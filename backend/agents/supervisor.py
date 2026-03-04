"""
Supervisor – LangGraph Multi-Agent Orchestrator
Coordinates FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT agents in parallel,
then runs Claude Sonnet as the senior analyst for final assessment.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from .finint_agent import run_finint_agent
from .geoint_agent import run_geoint_agent
from .news_agent import run_news_agent
from .sigint_agent import run_sigint_agent
from .socmint_agent import run_socmint_agent
from .techint_agent import run_techint_agent


# ── State ──────────────────────────────────────────────────────────────────

class AnalysisState(TypedDict, total=False):
    conflict: str
    finint_result: Dict[str, Any]
    sigint_result: Dict[str, Any]
    news_result: Dict[str, Any]
    geoint_result: Dict[str, Any]
    socmint_result: Dict[str, Any]
    techint_result: Dict[str, Any]
    escalation_score: float
    threat_level: str
    key_findings: List[str]
    scenarios: List[Dict[str, Any]]
    summary: str


# ── Intelligence Collection Node (all 6 agents in parallel) ─────────────────

# Per-agent timeout (seconds). Prevents one slow API from blocking the whole run.
_AGENT_TIMEOUT = 75


def _result_or_fallback(future, agent_name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Get future.result() with timeout; return fallback on timeout or error."""
    try:
        return future.result(timeout=_AGENT_TIMEOUT)
    except Exception as e:
        return {**fallback, "error": str(e), "timeout_or_error": True}


def collection_node(state: AnalysisState) -> AnalysisState:
    """Run all 6 intelligence agents in parallel with per-agent timeout."""
    conflict = state.get("conflict") or ""

    with ThreadPoolExecutor(max_workers=6) as executor:
        finint_f   = executor.submit(run_finint_agent, conflict)
        sigint_f   = executor.submit(run_sigint_agent, conflict)
        news_f     = executor.submit(run_news_agent, conflict)
        geoint_f   = executor.submit(run_geoint_agent, conflict)
        socmint_f  = executor.submit(run_socmint_agent, conflict)
        techint_f  = executor.submit(run_techint_agent, conflict)

        finint_result   = _result_or_fallback(finint_f, "finint", {"escalation_score": 0.0, "brent": None, "polymarket": []})
        sigint_result   = _result_or_fallback(sigint_f, "sigint", {"sigint_score": 0.0, "aircraft": [], "ships": [], "conflict_reports": []})
        news_result     = _result_or_fallback(news_f, "news", {"news_score": 0.0, "articles": [], "summary": ""})
        geoint_result   = _result_or_fallback(geoint_f, "geoint", {"geoint_score": 0.0, "anomalies": [], "hotspots": []})
        socmint_result  = _result_or_fallback(socmint_f, "socmint", {"socmint_score": 0.0, "top_signals": []})
        techint_result  = _result_or_fallback(techint_f, "techint", {"techint_score": 0.0, "tech_indicators": [], "ioda_events": []})

    return {
        "finint_result":   finint_result,
        "sigint_result":   sigint_result,
        "news_result":     news_result,
        "geoint_result":   geoint_result,
        "socmint_result":  socmint_result,
        "techint_result":  techint_result,
    }


# ── Supervisor Node (Claude Sonnet as senior analyst) ─────────────────────

def supervisor_node(state: AnalysisState) -> AnalysisState:
    """Claude Sonnet synthesizes all 6 intelligence streams into a final assessment."""
    conflict        = state.get("conflict") or ""
    finint_result   = state.get("finint_result") or {}
    sigint_result   = state.get("sigint_result") or {}
    news_result     = state.get("news_result") or {}
    geoint_result   = state.get("geoint_result") or {}
    socmint_result  = state.get("socmint_result") or {}
    techint_result  = state.get("techint_result") or {}

    # Extract scores
    finint_score   = float(finint_result.get("escalation_score", 0.0))
    sigint_score   = float(sigint_result.get("sigint_score", 0.0))
    news_score     = float(news_result.get("news_score", 0.0))
    geoint_score   = float(geoint_result.get("geoint_score", 0.0))
    socmint_score  = float(socmint_result.get("socmint_score", 0.0))
    techint_score  = float(techint_result.get("techint_score", 0.0))

    # Weighted composite score
    # FININT 18% | SIGINT 22% | NEWS 18% | GEOINT 12% | SOCMINT 18% | TECHINT 12%
    combined_score = (
        finint_score   * 0.18 +
        sigint_score   * 0.22 +
        news_score     * 0.18 +
        geoint_score   * 0.12 +
        socmint_score  * 0.18 +
        techint_score  * 0.12
    )

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    # Haiku ist günstiger; für höhere Qualität: SUPERVISOR_MODEL=claude-sonnet-4-6 setzen
    model_name = os.getenv("SUPERVISOR_MODEL", "claude-haiku-4-5-20251001")
    model = ChatAnthropic(model=model_name, temperature=0.1)

    system_prompt = """You are a senior intelligence analyst with access to 6 intelligence streams:
- FININT: Financial markets and oil price indicators
- SIGINT: Military aircraft, naval vessels, and conflict intel reports (CriticalThreats, LongWarJournal, UnderstandingWar)  
- NEWS: Open-source media sentiment analysis
- GEOINT: Satellite thermal anomaly detection
- SOCMINT: Social media signals from Telegram, Reddit, and RSS
- TECHINT: Tech sector indicators, export control news, IODA internet outage events (escalation signal)

Analyze all streams holistically and return ONLY valid JSON with no markdown:
{
  "escalation_score": <number 0-100>,
  "threat_level": <"MINIMAL"|"LOW"|"ELEVATED"|"HIGH"|"CRITICAL">,
  "key_findings": [<array of concise finding strings>],
  "scenarios": [{"description": <string>, "probability": <0-1>}],
  "summary": "<2-3 sentence BLUF summary>"
}"""

    # Reduzierte Payload an Claude = weniger Input-Tokens = geringere Kosten
    def _trim(obj, list_key: str, max_items: int):
        if not isinstance(obj, dict) or list_key not in obj:
            return obj
        arr = obj.get(list_key)
        if isinstance(arr, list) and len(arr) > max_items:
            return {**obj, list_key: arr[:max_items]}
        return obj

    finint_slim = _trim(finint_result, "polymarket", 5)
    news_slim = _trim(_trim(news_result, "articles", 8), "key_findings", 5)
    geoint_slim = _trim(_trim(geoint_result, "anomalies", 15), "hotspots", 5)
    sigint_slim = _trim(_trim(_trim(sigint_result, "aircraft", 8), "ships", 5), "conflict_reports", 5)
    socmint_slim = _trim(socmint_result, "top_signals", 8)
    techint_slim = _trim(_trim(techint_result, "tech_indicators", 5), "ioda_events", 5)

    user_payload = {
        "conflict": conflict,
        "composite_score": combined_score,
        "agent_scores": {
            "finint": finint_score,
            "sigint": sigint_score,
            "news": news_score,
            "geoint": geoint_score,
            "socmint": socmint_score,
            "techint": techint_score,
        },
        "finint": finint_slim,
        "sigint": sigint_slim,
        "news": news_slim,
        "geoint": geoint_slim,
        "socmint": socmint_slim,
        "techint": techint_slim,
    }

    msg = model.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_payload, default=str)),
    ])
    content = msg.content if hasattr(msg, "content") else str(msg)
    if isinstance(content, list):
        content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)

    # JSON ggf. aus Markdown-Codeblock extrahieren (Claude antwortet oft mit ```json ... ```)
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
            "summary": f"Composite score {combined_score:.0f}/100 aus 6 Agenten. Einzelne Streams (News, SIGINT, etc.) unten.",
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
    """Public entrypoint – runs all 6 agents then supervisor synthesis."""
    result = _COMPILED_GRAPH.invoke({"conflict": conflict})
    return {
        "conflict": conflict,
        "finint":   result.get("finint_result", {}),
        "sigint":   result.get("sigint_result", {}),
        "news":     result.get("news_result", {}),
        "geoint":   result.get("geoint_result", {}),
        "socmint":  result.get("socmint_result", {}),
        "techint":  result.get("techint_result", {}),
        "escalation_score": result.get("escalation_score", 0.0),
        "threat_level":     result.get("threat_level", "MINIMAL"),
        "key_findings":     result.get("key_findings", []),
        "scenarios":        result.get("scenarios", []),
        "summary":          result.get("summary", ""),
    }
