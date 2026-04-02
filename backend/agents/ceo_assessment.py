"""
So-what assessment layer for CEO synthesis.

Goal: convert high-confidence findings into stakeholder-specific significance, trajectory,
concrete next steps, and explicit information gaps.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .llm import call_llm, get_model_name, require_api_key
from .utils import parse_llm_json

logger = logging.getLogger(__name__)


ASSESSMENT_SYSTEM_PROMPT = """You are a senior intelligence analyst writing an assessment for a specific stakeholder.
Your job: take the provided high-confidence findings and convert them into:
- what is happening (situation),
- why it matters to the stakeholder (significance),
- where it is likely heading (trajectory: 24h / 7d / 30d),
- concrete next steps with owners, timelines, rationales, and monitoring triggers,
- explicit information gaps and where to get the missing information.

Hard requirements:
- Return ONLY valid JSON (no markdown).
- Do not invent sources. If you recommend a gap-source, prefer general source types (e.g. SIGINT, official statements, commercial satellite, shipping/ADS-B, sanctions registries) or cite URLs that are present in the payload.
- Next steps must be specific and actionable. Avoid vague phrasing ("monitor the situation").

Output schema (exact keys):
{
  "assessment": {
    "situation": "2-3 sentences",
    "significance": "Why it matters for the stakeholder",
    "trajectory": {
      "h24": "24h outlook",
      "d7": "7d outlook",
      "d30": "30d outlook"
    },
    "next_steps": [
      {
        "action": "Concrete action",
        "who": "Role/team who should act",
        "timeline": "By when",
        "rationale": "Why now",
        "monitoring_trigger": "Signal that indicates escalation / re-evaluation"
      }
    ],
    "information_gaps": ["What we do not know + where to get it"],
    "information_gaps_structured": [
      {
        "gap": "What we do not know",
        "recommended_sources": [
          {
            "type": "MOVINT|SIGINT|GEOINT|OSINT|DIPLO|CYBER|MARITIME",
            "provider": "ADS-B Exchange|FlightRadar24|Planet|Sentinel Hub|MarineTraffic|official|wire|other",
            "how": "What to query / monitor",
            "reference_urls": ["https://... optional; prefer provided provenance_urls"]
          }
        ]
      }
    ]
  }
}"""


def _default_stakeholder_context() -> Dict[str, Any]:
    raw = (os.getenv("CEO_STAKEHOLDER_CONTEXT") or "").strip()
    if not raw:
        return {
            "persona": "general",
            "audience": "general intelligence consumer",
            "objectives": ["situational awareness", "risk posture", "decision support"],
            "constraints": [],
        }
    # Allow simple string persona names to be used without JSON.
    if raw and not raw.lstrip().startswith("{"):
        return {"persona": raw, "audience": raw, "objectives": [], "constraints": []}
    try:
        import json

        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"persona": "general", "audience": "general"}
    except Exception:
        return {"persona": "general", "audience": "general"}


def _normalize_assessment(parsed: Any) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    a = parsed.get("assessment")
    if not isinstance(a, dict):
        return {}

    situation = str(a.get("situation") or "").strip()
    significance = str(a.get("significance") or "").strip()

    traj = a.get("trajectory") or {}
    if isinstance(traj, str):
        traj = {"h24": traj[:400], "d7": "", "d30": ""}
    if not isinstance(traj, dict):
        traj = {}
    trajectory = {
        "h24": str(traj.get("h24") or traj.get("24h") or "").strip()[:800],
        "d7": str(traj.get("d7") or traj.get("7d") or "").strip()[:800],
        "d30": str(traj.get("d30") or traj.get("30d") or "").strip()[:800],
    }

    next_steps_in = a.get("next_steps") or []
    next_steps: List[Dict[str, str]] = []
    if isinstance(next_steps_in, list):
        for item in next_steps_in[:12]:
            if isinstance(item, str) and item.strip():
                next_steps.append(
                    {
                        "action": item.strip()[:260],
                        "who": "analyst",
                        "timeline": "24h",
                        "rationale": "",
                        "monitoring_trigger": "",
                    }
                )
            elif isinstance(item, dict):
                action = str(item.get("action") or "").strip()
                if not action:
                    continue
                next_steps.append(
                    {
                        "action": action[:260],
                        "who": str(item.get("who") or item.get("owner") or "analyst").strip()[:120],
                        "timeline": str(item.get("timeline") or item.get("time_horizon") or "24h").strip()[:64],
                        "rationale": str(item.get("rationale") or item.get("why") or "").strip()[:800],
                        "monitoring_trigger": str(item.get("monitoring_trigger") or "").strip()[:500],
                    }
                )

    gaps_in = a.get("information_gaps") or []
    information_gaps: List[str] = []
    if isinstance(gaps_in, list):
        for g in gaps_in[:20]:
            if isinstance(g, str) and g.strip():
                information_gaps.append(g.strip()[:260])

    structured_in = a.get("information_gaps_structured") or a.get("information_gaps_struct") or []
    information_gaps_structured: List[Dict[str, Any]] = []
    if isinstance(structured_in, list):
        for gi in structured_in[:20]:
            if not isinstance(gi, dict):
                continue
            gap = str(gi.get("gap") or gi.get("question") or "").strip()
            if not gap:
                continue
            recs_in = gi.get("recommended_sources") or gi.get("sources") or []
            recs: List[Dict[str, Any]] = []
            if isinstance(recs_in, list):
                for r in recs_in[:8]:
                    if not isinstance(r, dict):
                        continue
                    r_type = str(r.get("type") or "").strip()[:40]
                    provider = str(r.get("provider") or r.get("source") or "").strip()[:80]
                    how = str(r.get("how") or r.get("query") or r.get("notes") or "").strip()[:260]
                    refs_in = r.get("reference_urls") or r.get("refs") or []
                    refs: List[str] = []
                    if isinstance(refs_in, list):
                        for u in refs_in[:6]:
                            if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                                refs.append(u.strip())
                    recs.append(
                        {"type": r_type, "provider": provider, "how": how, "reference_urls": refs}
                    )
            information_gaps_structured.append({"gap": gap[:260], "recommended_sources": recs})

    if not situation and not significance and not next_steps and not information_gaps:
        return {}

    return {
        "assessment": {
            "situation": situation[:1200],
            "significance": significance[:1200],
            "trajectory": trajectory,
            "next_steps": next_steps[:10],
            "information_gaps": information_gaps[:12],
            "information_gaps_structured": information_gaps_structured[:12],
        }
    }


def build_rule_based_assessment(
    *,
    stakeholder: Dict[str, Any],
    summary: str,
    findings: List[str],
) -> Dict[str, Any]:
    persona = str(stakeholder.get("persona") or stakeholder.get("audience") or "general").strip() or "general"
    situation = summary.strip()[:900] if summary else ""
    if not situation:
        situation = "Signals indicate a developing situation with multiple corroborating streams."

    # Minimal but always-present actionable scaffold.
    next_steps = [
        {
            "action": "Validate top high-confidence claims against primary/credible sources and corroborate across streams.",
            "who": "analyst",
            "timeline": "now",
            "rationale": "Prevents acting on single-stream noise while preserving speed in escalation windows.",
            "monitoring_trigger": "Two independent streams corroborate a major shift (e.g. kinetic event + official statement / sensor confirmation).",
        },
        {
            "action": "Set explicit alert thresholds for sudden multi-stream score jumps and degraded-stream recoveries.",
            "who": "ops",
            "timeline": "24h",
            "rationale": "Degraded feeds can mask risk; recoveries can create apparent jumps that need interpretation.",
            "monitoring_trigger": "Any stream flips from degraded→live while composite score rises >10 points in 24h.",
        },
    ]
    gaps = [
        "We lack corroborating official/SIGINT confirmation for key claims (seek: official statements, trusted wire services, partner intel summaries).",
        "We lack independent movement confirmation (seek: ADS-B / airlift patterns; maritime AIS patterns if relevant).",
        "We lack independent geospatial confirmation for reported movements (seek: commercial satellite imagery / change detection over key AOIs).",
    ]
    if findings:
        gaps.insert(0, f"We have limited attribution detail for: {findings[0][:160]}")

    gaps_structured = [
        {
            "gap": "Do we have independent confirmation of military transport flights / airbridge patterns?",
            "recommended_sources": [
                {
                    "type": "MOVINT",
                    "provider": "ADS-B Exchange",
                    "how": "Query military/cargo flights into/out of key airports; watch sudden spikes, route changes, and callsign clusters.",
                    "reference_urls": ["https://www.adsbexchange.com/"],
                }
            ],
        },
        {
            "gap": "Can we independently verify reported troop/equipment movements on the ground?",
            "recommended_sources": [
                {
                    "type": "GEOINT",
                    "provider": "Planet",
                    "how": "Task AOIs for daily revisit; run change detection on staging areas, airbases, ports, depots.",
                    "reference_urls": ["https://www.planet.com/"],
                },
                {
                    "type": "GEOINT",
                    "provider": "Sentinel Hub",
                    "how": "Use Sentinel-2/S1 time series for low-cost monitoring; look for new vehicle tracks, disturbed ground, smoke/plumes.",
                    "reference_urls": ["https://www.sentinel-hub.com/"],
                },
            ],
        },
        {
            "gap": "If maritime impact is plausible, do we see anomalous tanker/merchant behavior near chokepoints?",
            "recommended_sources": [
                {
                    "type": "MARITIME",
                    "provider": "MarineTraffic",
                    "how": "Monitor AIS density, route deviations, loitering, dark periods near chokepoints; compare vs 30d baseline.",
                    "reference_urls": ["https://www.marinetraffic.com/"],
                }
            ],
        },
    ]

    return {
        "assessment": {
            "situation": situation,
            "significance": f"Implications are framed for stakeholder persona '{persona}'.",
            "trajectory": {"h24": "", "d7": "", "d30": ""},
            "next_steps": next_steps,
            "information_gaps": gaps,
            "information_gaps_structured": gaps_structured,
        }
    }


def run_ceo_assessment(
    *,
    conflict: str,
    supervisor_payload: Dict[str, Any],
    high_conf_findings: List[Dict[str, Any]],
    summary: str,
    stakeholder_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assessment LLM call. Returns normalized dict with key "assessment", or a rule-based fallback.
    """
    stakeholder = stakeholder_context or _default_stakeholder_context()
    user_payload = {
        "conflict": conflict,
        "stakeholder": stakeholder,
        "high_confidence_findings": high_conf_findings[:12],
        # Keep some global context available (degraded streams, temporal, etc.).
        "context": {
            "threat_level": supervisor_payload.get("threat_level"),
            "composite_score": supervisor_payload.get("composite_score"),
            "degraded_agents": supervisor_payload.get("degraded_agents") or [],
            "agent_score_temporal": supervisor_payload.get("agent_score_temporal") or {},
            "data_quality_gate": supervisor_payload.get("data_quality_gate") or {},
        },
        "summary": summary[:1400] if isinstance(summary, str) else str(summary)[:1400],
        # Give the model provenance URLs if available so it can ground gap-source suggestions.
        "provenance_urls": supervisor_payload.get("provenance_urls") or [],
    }

    tried_model = None
    try:
        require_api_key()
        model = get_model_name("assessment")
        tried_model = model
        import json

        raw = call_llm(
            system=ASSESSMENT_SYSTEM_PROMPT,
            user_content=json.dumps(user_payload, default=str)[:250_000],
            model=model,
            temperature=0.2,
        )
        parsed = parse_llm_json(raw) if raw else None
        out = _normalize_assessment(parsed)
        if out:
            out["_meta"] = {"mode": "llm", "model": model}
            return out
    except Exception as e:
        logger.warning("CEO assessment failed (model=%s): %s", tried_model, e)

    fb = build_rule_based_assessment(
        stakeholder=stakeholder,
        summary=summary,
        findings=[f.get("finding", "") for f in (high_conf_findings or []) if isinstance(f, dict) and f.get("finding")],
    )
    fb["_meta"] = {"mode": "rule_based", "reason": "llm_unavailable_or_invalid"}
    return fb

