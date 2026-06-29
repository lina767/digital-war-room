"""LLM-powered research enrichment for conflict analysis.

Historically routed through Gemini; now delegates to Anthropic/OpenAI via the
shim in ``services.gemini_service`` (kept for call-site stability).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from agents.research_contracts import ResearchEnrichmentResult, ResearchUsage
from agents.research_normalizer import normalize_research_enrichments
from agents.research_trigger import REQUIRED_FIELD_RULES, evaluate_research_trigger
from services.gemini_service import default_research_budget, evaluate_budget, run_gemini_research


def _snapshot_for_prompt(agent_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    keep: Dict[str, Any] = {}
    for agent, block in agent_results.items():
        if not isinstance(block, dict):
            continue
        keep[agent] = {
            "summary": block.get("summary"),
            "dq_confidence": block.get("dq_confidence"),
            "data_freshness": block.get("data_freshness"),
            "provenance_refs": (block.get("provenance_refs") or [])[:6],
        }
    return keep


def _required_fields_status(agent_results: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
    status: Dict[str, bool] = {}
    for field_path, expected in REQUIRED_FIELD_RULES.items():
        agent, field = field_path.split(".", 1)
        block = agent_results.get(agent) or {}
        value = block.get(field) if isinstance(block, dict) else None
        if expected is list:
            status[field_path] = isinstance(value, list) and len(value) > 0
        elif expected is dict:
            status[field_path] = isinstance(value, dict) and len(value) > 0
        else:
            status[field_path] = value is not None
    return status


def _build_prompt(
    *,
    conflict: str,
    trigger_decision: Dict[str, Any],
    required_status: Dict[str, bool],
    snapshot: Dict[str, Any],
) -> str:
    return (
        "You are a strict OSINT research assistant. Return ONLY valid JSON.\n"
        "Language policy: ALL output text must be in English.\n"
        "Task:\n"
        "1) Propose enrichments only for missing/stale/conflicting fields.\n"
        "1b) If provenance coverage is low, prioritize adding direct source URLs for the highest-impact missing fields.\n"
        "2) EVERY enrichment MUST include a direct source_url (http/https).\n"
        "3) If you do not have a source URL, do NOT propose that enrichment.\n\n"
        "Return JSON with this shape:\n"
        '{'
        '"analysis_en": "short assessment in English", '
        '"air_activity_assessment_en": "if SIGINT aircraft activity exists, assess who is airborne and implications for Iran conflict in English", '
        '"findings": ["short insight"], '
        '"findings_en": ["short insight in English"], '
        '"enrichments": ['
        '{"field_path":"agent.field","value":"...","source_url":"https://...","source_title":"...","fetched_at":"ISO-8601","confidence":70,"note":"..."}'
        "]"
        "}\n\n"
        f"Conflict: {conflict}\n"
        f"TriggerDecision: {json.dumps(trigger_decision, default=str)[:6000]}\n"
        f"RequiredFieldStatus: {json.dumps(required_status, default=str)}\n"
        f"AgentSnapshot: {json.dumps(snapshot, default=str)[:9000]}"
    )


def _sigint_aircraft_assessment_en(agent_results: Dict[str, Dict[str, Any]]) -> str:
    sigint = agent_results.get("sigint") or {}
    if not isinstance(sigint, dict):
        return ""
    aircraft = sigint.get("aircraft")
    if not isinstance(aircraft, list) or len(aircraft) == 0:
        return ""

    cleaned = []
    military_count = 0
    for row in aircraft[:20]:
        if not isinstance(row, dict):
            continue
        callsign = str(row.get("callsign") or row.get("flight") or row.get("hex") or "").strip()
        ac_type = str(row.get("type") or row.get("aircraft_type") or "").strip()
        desc = str(row.get("category") or row.get("description") or "").lower()
        if any(k in desc for k in ("military", "transport", "fighter", "tanker", "surveillance")):
            military_count += 1
        if callsign or ac_type:
            cleaned.append((callsign or "unknown", ac_type or "unknown"))

    if len(cleaned) == 0:
        return ""

    sample = ", ".join([f"{c} ({t})" for c, t in cleaned[:4]])
    implication = (
        "This pattern suggests active air-tasking, readiness signaling, and potentially logistics or ISR support "
        "around sensitive theaters linked to the Iran conflict. It raises near-term escalation risk if sorties "
        "cluster near contested corridors or coincide with maritime and missile-warning indicators."
    )
    return (
        f"SIGINT observed {len(cleaned)} tracked aircraft (sample: {sample}). "
        f"At least {military_count} entries appear military-oriented. {implication}"
    )


def run_research_enrichment(
    *,
    conflict: str,
    agent_results: Dict[str, Dict[str, Any]],
    data_quality_gate: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    trigger_decision = evaluate_research_trigger(
        conflict=conflict,
        agent_results=agent_results,
        data_quality_gate=data_quality_gate,
    )
    budget = default_research_budget()
    usage = ResearchUsage()
    budget_status = evaluate_budget(usage, budget)

    required_before = _required_fields_status(agent_results)
    result = ResearchEnrichmentResult(
        triggered=trigger_decision.triggered,
        trigger_decision=trigger_decision,
        budget_status=budget_status,
        publish_decision="auto_publish",
    )
    if not trigger_decision.triggered or not budget_status.allowed:
        return {
            **result.model_dump(mode="json"),
            "required_field_coverage_before": {
                "filled_required_fields": sum(1 for ok in required_before.values() if ok),
                "total_required_fields": len(required_before),
            },
            "required_field_coverage_after": {
                "filled_required_fields": sum(1 for ok in required_before.values() if ok),
                "total_required_fields": len(required_before),
            },
        }

    prompt = _build_prompt(
        conflict=conflict,
        trigger_decision=trigger_decision.model_dump(mode="json"),
        required_status=required_before,
        snapshot=_snapshot_for_prompt(agent_results),
    )
    gem = run_gemini_research(prompt)
    usage = ResearchUsage(
        requests=1,
        input_tokens=gem.input_tokens,
        output_tokens=gem.output_tokens,
        estimated_cost_usd=round(gem.cost_usd, 8),
    )
    budget_status = evaluate_budget(usage, budget)

    findings: List[str] = []
    analysis_en = ""
    air_activity_assessment_en = _sigint_aircraft_assessment_en(agent_results)
    raw_enrichments: List[Dict[str, Any]] = []
    if isinstance(gem.parsed_json, dict):
        findings_src = gem.parsed_json.get("findings_en")
        if not isinstance(findings_src, list):
            findings_src = gem.parsed_json.get("findings")
        findings = [str(x) for x in (findings_src or []) if isinstance(x, str)][:10]
        analysis_en = str(gem.parsed_json.get("analysis_en") or "").strip()
        model_air = str(gem.parsed_json.get("air_activity_assessment_en") or "").strip()
        if model_air:
            air_activity_assessment_en = model_air
        if isinstance(gem.parsed_json.get("enrichments"), list):
            raw_enrichments = [x for x in gem.parsed_json["enrichments"] if isinstance(x, dict)]

    applied, rejected, source_ratio = normalize_research_enrichments(raw_enrichments)
    # Publish policy: enforce review when source coverage is incomplete or high-severity trigger exists.
    high_severity = any(r.severity == "high" for r in trigger_decision.reasons)
    publish_decision = "human_review" if (source_ratio < 1.0 or high_severity or len(rejected) > 0) else "auto_publish"

    after_status = dict(required_before)
    for item in applied:
        after_status[item.field_path] = True

    final = ResearchEnrichmentResult(
        triggered=trigger_decision.triggered,
        trigger_decision=trigger_decision,
        budget_status=budget_status,
        publish_decision=publish_decision,
        analysis_en=analysis_en,
        air_activity_assessment_en=air_activity_assessment_en,
        findings=findings,
        enrichments_applied=applied,
        enrichments_rejected=rejected,
        source_coverage_ratio=round(source_ratio, 3),
    )
    out = final.model_dump(mode="json")
    out["required_field_coverage_before"] = {
        "filled_required_fields": sum(1 for ok in required_before.values() if ok),
        "total_required_fields": len(required_before),
    }
    out["required_field_coverage_after"] = {
        "filled_required_fields": sum(1 for ok in after_status.values() if ok),
        "total_required_fields": len(after_status),
    }
    if gem.error:
        out["research_llm_error"] = gem.error
    return out
