"""CEO output normalization, rule-based summary, provenance, and API response shape."""

import json
from typing import Any, Dict, List, Optional

from .ceo_scoring import degraded_streams_caveat
from .division import DivisionResult

PROVENANCE_AGENT_KEYS = [
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "mediaint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
    "pentagon",
]

API_AGENT_NAMES = [
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "mediaint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
    "pentagon",
]


def normalize_finding_confidence(val: Any) -> str:
    s = str(val).strip().lower()
    if s in ("high", "h", "3"):
        return "high"
    if s in ("low", "l", "1"):
        return "low"
    return "medium"


def align_key_findings_confidence(findings: List[str], conf: List[str]) -> List[str]:
    """Pad or trim confidence list to match key_findings length (default medium)."""
    out = list(conf[: len(findings)])
    while len(out) < len(findings):
        out.append("medium")
    return out


def normalize_root_cause_suggestions(raw: Any) -> List[Dict[str, str]]:
    """Parse CEO JSON root_cause_suggestions: list of objects or 'signal → cause' strings."""
    out: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:8]:
        if isinstance(item, str):
            s = item.strip()
            sep = "→" if "→" in s else ("->" if "->" in s else "")
            if sep:
                parts = s.split(sep, 1)
                signal = parts[0].strip()
                likely = parts[1].strip() if len(parts) > 1 else ""
                if signal and likely:
                    out.append({"signal": signal, "likely_cause": likely, "confidence": "medium"})
            continue
        if isinstance(item, dict):
            sig = str(item.get("signal") or item.get("observation") or "").strip()
            cause = str(item.get("likely_cause") or item.get("cause") or item.get("driver") or "").strip()
            conf = str(item.get("confidence") or "medium").strip().lower()
            if conf not in ("high", "medium", "low"):
                conf = "medium"
            if sig and cause:
                out.append({"signal": sig, "likely_cause": cause, "confidence": conf})
    return out[:6]


def normalize_next_steps(raw: Any) -> List[Dict[str, Any]]:
    """
    Parse CEO JSON next_steps into a list of dicts:
    {"action","owner","time_horizon","why","source_refs","confidence"}.
    """
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw[:12]:
        if isinstance(item, str):
            s = item.strip()
            if not s:
                continue
            out.append(
                {
                    "action": s[:240],
                    "owner": "analyst",
                    "time_horizon": "24h",
                    "why": "",
                    "source_refs": [],
                    "confidence": "medium",
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or item.get("step") or item.get("task") or "").strip()
        if not action:
            continue
        owner = str(item.get("owner") or "analyst").strip().lower()
        if owner not in ("analyst", "ops", "exec"):
            owner = "analyst"
        time_horizon = str(item.get("time_horizon") or item.get("horizon") or "24h").strip().lower()
        if time_horizon not in ("now", "24h", "7d"):
            time_horizon = "24h"
        why = str(item.get("why") or item.get("rationale") or "").strip()
        conf = str(item.get("confidence") or "medium").strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        src = item.get("source_refs") or item.get("sources") or item.get("refs") or []
        refs: List[str] = []
        if isinstance(src, list):
            for u in src[:10]:
                if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                    refs.append(u.strip())
        out.append(
            {
                "action": action[:240],
                "owner": owner,
                "time_horizon": time_horizon,
                "why": why[:600],
                "source_refs": refs,
                "confidence": conf,
            }
        )
    return out[:10]


def heuristic_root_causes(
    energy_result: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Deterministic hypotheses when the LLM omits root_cause_suggestions."""
    out: List[Dict[str, str]] = []
    seen_sig: set[str] = set()

    def add(signal: str, likely_cause: str, confidence: str) -> None:
        if signal in seen_sig:
            return
        seen_sig.add(signal)
        out.append({"signal": signal, "likely_cause": likely_cause, "confidence": confidence})

    note = energy_result.get("global_impact_note")
    if isinstance(note, str) and note.strip():
        lower = note.lower()
        if any(x in lower for x in ("hormuz", "chokepoint", "brent", "wti", "strait")):
            add("Elevated oil / energy risk premium", note.strip()[:220], "medium")

    cps = chokepoint_result.get("chokepoints") or []
    if isinstance(cps, list):
        for cp in cps:
            if not isinstance(cp, dict):
                continue
            name = str(cp.get("name") or "")
            risk = cp.get("disruption_risk")
            if "hormuz" in name.lower() and isinstance(risk, (int, float)) and risk >= 35:
                add(
                    f"{name} disruption risk {risk:.0f}/100",
                    "Tanker traffic density, incident reporting, or closure rhetoric in coverage — see chokepoint panel",
                    "high" if risk >= 65 else "medium",
                )
                break

    commodities = energy_result.get("commodities") or []
    if isinstance(commodities, list) and not any("move" in x.get("signal", "").lower() for x in out):
        for c in commodities:
            if not isinstance(c, dict):
                continue
            sym = str(c.get("symbol") or "").upper()
            raw_ch = c.get("change_pct_raw")
            if sym in ("BRENT", "WTI", "CL", "BZ") and isinstance(raw_ch, (int, float)) and abs(raw_ch) >= 1.5:
                add(
                    f"{sym} {raw_ch:+.1f}% (session)",
                    "Geopolitical risk premium — cross-check with Hormuz/Bab el-Mandeb and FININT",
                    "medium",
                )
                break

    fsr = energy_result.get("food_security_risk")
    if isinstance(fsr, (int, float)) and fsr >= 55:
        add(
            f"Food security stress {fsr:.0f}/100",
            "Grain/fertilizer prices and route exposure (incl. chokepoints affecting flows)",
            "low" if fsr < 70 else "medium",
        )

    return out[:5]


def build_rule_based_ceo_summary(
    conflict: str,
    composite: float,
    threat_level: str,
    division_results: Dict[str, DivisionResult],
    *,
    degraded_agents: Optional[List[str]] = None,
) -> str:
    """
    Build a deterministic 2-3 sentence CEO recap when LLM synthesis is unavailable.
    """
    degraded_agents = degraded_agents or []
    ordered = sorted(division_results.items(), key=lambda x: -x[1].score)
    top_name, top_result = ordered[0] if ordered else ("overall", None)
    second_name, second_result = ordered[1] if len(ordered) > 1 else (None, None)

    sentence_1 = (
        f"{conflict}: overall escalation is {composite:.0f}/100 ({threat_level}), "
        f"driven primarily by {top_name} signals."
    )

    sentence_2 = ""
    if second_name and second_result is not None:
        sentence_2 = (
            f"Secondary pressure comes from {second_name} indicators "
            f"(score {second_result.score:.0f}) while {top_name} remains elevated "
            f"(score {top_result.score:.0f})."
        )
    elif top_result is not None:
        sentence_2 = f"{top_name.title()} indicators are currently the dominant risk driver."

    anomaly_notes: List[str] = []
    for name, dr in ordered:
        if not dr.anomalies:
            continue
        # Keep only the first anomaly per division to avoid noisy recaps.
        first = dr.anomalies[0]
        anomaly_notes.append(f"{name}: {first.description}")
        if len(anomaly_notes) >= 2:
            break

    if anomaly_notes:
        sentence_3 = f"Watch items: {'; '.join(anomaly_notes)}."
        body = f"{sentence_1} {sentence_2} {sentence_3}".strip()
    else:
        body = f"{sentence_1} {sentence_2}".strip()

    if degraded_agents:
        return f"{degraded_streams_caveat(degraded_agents)}\n\n{body}".strip()
    return body


def build_provenance_index(agent_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    provenance_index: List[Dict[str, Any]] = []
    for pname in PROVENANCE_AGENT_KEYS:
        raw = agent_results.get(pname) or {}
        meta = raw.get("_meta") if isinstance(raw, dict) else None
        if not isinstance(meta, dict):
            meta = {}
        sources = meta.get("sources") or []
        n_src = len(sources) if isinstance(sources, list) else 0
        ok_n = 0
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict) and s.get("status") in ("ok", "degraded"):
                    ok_n += 1
        steps = meta.get("processing_steps") or []
        n_steps = len(steps) if isinstance(steps, list) else 0
        provenance_index.append(
            {
                "agent": pname,
                "fetched_at": meta.get("fetched_at"),
                "duration_ms": meta.get("duration_ms"),
                "sources_total": n_src,
                "sources_ok": ok_n,
                "data_confidence": meta.get("data_confidence"),
                "processing_steps_count": n_steps,
            }
        )
    return provenance_index


def assemble_ceo_response(
    *,
    conflict: str,
    synthesis_score: float,
    threat_level: str,
    key_findings: List[str],
    key_findings_context: List[str],
    key_findings_confidence: List[str],
    next_steps: List[Dict[str, Any]],
    scenarios: List[Any],
    summary: str,
    narrative_story: str,
    actors: List[Any],
    predictive: Dict[str, Any],
    compliance: Dict[str, Any],
    alerts: List[Any],
    synthesis_meta: Dict[str, Any],
    agent_data_confidence: Dict[str, str],
    degraded_agents: List[str],
    temporal_context: Dict[str, Any],
    analysis_run_id: str,
    provenance_index: List[Dict[str, Any]],
    qf: Dict[str, Any],
    data_quality_gate: Dict[str, Any],
    research_enrichment: Dict[str, Any],
    store: Any,
    division_results: Dict[str, DivisionResult],
    as_dict_fn: Any,
) -> Dict[str, Any]:
    """Build backwards-compatible CEO API dict and attach per-agent payloads from store."""
    response: Dict[str, Any] = {
        "conflict": conflict,
        "escalation_score": round(synthesis_score, 1),
        "threat_level": threat_level,
        "key_findings": key_findings,
        "key_findings_context": key_findings_context,
        "key_findings_confidence": key_findings_confidence,
        "next_steps": next_steps,
        "corroborated_patterns": [],
        "scenarios": scenarios,
        "summary": summary,
        "narrative_story": narrative_story,
        "actors": actors,
        "predictive": predictive,
        "compliance": compliance,
        "alerts": alerts,
        "pattern_flags": [],
        "synthesis_meta": synthesis_meta,
        "agent_data_confidence": agent_data_confidence,
        "degraded_agents": degraded_agents,
        "temporal_context": temporal_context,
        "analysis_run_id": analysis_run_id,
        "provenance_index": provenance_index,
        "cross_validation": qf,
        "data_quality_gate": data_quality_gate,
        "quality_warnings": list(data_quality_gate.get("quality_warnings") or []),
        "research_enrichment": research_enrichment if isinstance(research_enrichment, dict) else {},
        "review_decision": (
            "human_review"
            if str((research_enrichment or {}).get("publish_decision", "")).strip().lower() == "human_review"
            else "auto_publish"
        ),
        "analysis_result_schema_version": 2,
    }

    for agent_name in API_AGENT_NAMES:
        raw_result = store.get(agent_name)
        response[agent_name] = as_dict_fn(raw_result) if raw_result else {}

    response["divisions"] = {name: dr.model_dump(mode="json") for name, dr in division_results.items()}

    # Outcome/quality metrics (compact, UI-friendly)
    prov_total = 0
    prov_ok = 0
    for agent_name in PROVENANCE_AGENT_KEYS:
        block = response.get(agent_name) or {}
        if not isinstance(block, dict):
            continue
        prov_total += 1
        refs = block.get("provenance_refs") or []
        if isinstance(refs, list) and any(
            isinstance(u, str) and u.strip().startswith(("http://", "https://")) for u in refs
        ):
            prov_ok += 1
    provenance_coverage = (prov_ok / prov_total) if prov_total else 0.0

    ns_total = len(next_steps) if isinstance(next_steps, list) else 0
    ns_ok = 0
    if isinstance(next_steps, list):
        for ns in next_steps:
            if isinstance(ns, dict) and isinstance(ns.get("source_refs"), list) and len(ns.get("source_refs") or []) > 0:
                ns_ok += 1
    next_steps_source_coverage = (ns_ok / ns_total) if ns_total else 0.0

    news_block = response.get("news") or {}
    socmint_block = response.get("socmint") or {}
    news_articles_count = (
        len(news_block.get("articles") or []) if isinstance(news_block, dict) and isinstance(news_block.get("articles"), list) else 0
    )
    socmint_total_signals = (
        int(socmint_block.get("total_signals") or 0) if isinstance(socmint_block, dict) else 0
    )

    response["coverage_metrics"] = {
        "provenance_coverage": round(float(provenance_coverage), 3),
        "provenance_coverage_agents_ok": prov_ok,
        "provenance_coverage_agents_total": prov_total,
        "next_steps_source_coverage": round(float(next_steps_source_coverage), 3),
        "next_steps_with_sources": ns_ok,
        "next_steps_total": ns_total,
        "news_articles_count": news_articles_count,
        "socmint_total_signals": socmint_total_signals,
    }

    return response
