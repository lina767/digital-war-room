"""
Cross-stream narrative synthesis: one cohesive causal story from all agent outputs.

Complements per-agent scores with an LLM-written chain of reasoning (e.g. markets → SIGINT → chokepoints).
"""

import json
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_MAX_NARRATIVE_PAYLOAD_CHARS = 120_000

_NARRATIVE_SYSTEM = """You are an intelligence analyst writing one cohesive operational narrative for decision-makers.

Structure (follow this flow):
1) Open with the current situation in one or two sentences (what is happening in the theater).
2) Explain how the main streams reinforce or qualify each other — not a list of separate scores. Use causal
   language: therefore, meanwhile, which suggests, in parallel, reinforcing, offsetting. Arrows "→" between
   clauses are fine when they aid scanning.
3) Close with implications or what to watch next (one sentence), tied to the conflict.

Formatting:
- Write in English only (no German or other languages).
- Use 2–4 short paragraphs separated by a blank line between paragraphs (double newline in plain text).
- Each paragraph: 2–4 sentences. No bullet lists, no markdown headings, no JSON.
- Name streams when useful: FININT, SIGINT, NEWS, GEOINT, SATINTEL, SOCMINT, MEDIAINT, TECHINT, CYBER, ENERGY,
  DIPLO, PROXIMITY, CHOKEPOINT, PENTAGON (informal DC venue proxy only), Signal Framework (payload key "narrative") when present.
- If two signals contradict, say so briefly and which stream is softer evidence.
- If PAYLOAD_JSON includes "degraded_agents" (non-empty), name those streams and clarify that low scores there reflect missing feeds, not necessarily calm conditions.
- Stay under ~450 words."""

_AGENT_ORDER = (
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
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
    "pentagon",
)


def _fallback_narrative(agent_outputs: Dict[str, Any]) -> str:
    """Deterministic recap when LLM is unavailable."""
    conflict = str(agent_outputs.get("conflict") or "theater").strip() or "theater"
    scores = agent_outputs.get("agent_scores")
    if not isinstance(scores, dict):
        return f"{conflict}: Multi-stream assessment pending; per-agent summaries were not available for a connected narrative."

    ranked = sorted(
        ((k, float(v)) for k, v in scores.items() if isinstance(v, (int, float))),
        key=lambda x: -x[1],
    )[:5]
    if not ranked:
        return f"{conflict}: Insufficient scored streams to build a cross-stream story."

    parts = [
        f"{conflict}: the strongest scored streams right now are "
        + ", ".join(f"{k} ({v:.0f})" for k, v in ranked[:3])
        + "."
    ]
    for name in ("finint", "sigint", "chokepoint", "energy"):
        blob = agent_outputs.get(name)
        if isinstance(blob, dict):
            s = blob.get("summary")
            if isinstance(s, str) and s.strip():
                excerpt = s.strip()[:220] + ("…" if len(s) > 220 else "")
                parts.append(f"From {name.upper()}, the picture is: {excerpt}")
                break
    return "\n\n".join(parts)


def synthesize_narrative(agent_outputs: Dict[str, Any]) -> str:
    """
    Turn multi-agent JSON into one cohesive causal story in English (Claude Haiku by default; fallback on error).

    Expected shape: same as CEO supervisor payload — conflict, threat_level, composite_score, agent_scores,
    and per-agent compact dicts (finint, sigint, news, ...).
    """
    try:
        from .llm import LLMCreditExhaustedError, call_llm, get_model_name, require_api_key

        require_api_key()
    except Exception as e:
        logger.debug("Narrative synthesis skipped (no API / key): %s", e)
        return _fallback_narrative(agent_outputs)

    slim: Dict[str, Any] = {
        "conflict": agent_outputs.get("conflict"),
        "composite_score": agent_outputs.get("composite_score"),
        "threat_level": agent_outputs.get("threat_level"),
        "division_composite_score": agent_outputs.get("division_composite_score"),
        "division_scores": agent_outputs.get("division_scores"),
        "agent_scores": agent_outputs.get("agent_scores"),
        "agent_data_confidence": agent_outputs.get("agent_data_confidence"),
        "degraded_agents": agent_outputs.get("degraded_agents"),
        "acled_reference_analyses": agent_outputs.get("acled_reference_analyses"),
    }
    for k in _AGENT_ORDER:
        if k in agent_outputs:
            slim[k] = agent_outputs[k]

    user_json = json.dumps(slim, default=str)
    if len(user_json) > _MAX_NARRATIVE_PAYLOAD_CHARS:
        user_json = user_json[:_MAX_NARRATIVE_PAYLOAD_CHARS]

    # Default: agent role = Claude Haiku on Anthropic (see llm.get_model_name("agent")).
    model_env = (os.getenv("NARRATIVE_SYNTHESIS_MODEL") or "").strip()
    model = model_env or get_model_name("agent")

    try:
        raw = call_llm(
            system=_NARRATIVE_SYSTEM,
            user_content=f"PAYLOAD_JSON:\n{user_json}",
            model=model,
            temperature=0.25,
            max_tokens=900,
        )
    except LLMCreditExhaustedError as e:
        logger.error("Narrative synthesis skipped — LLM credits exhausted: %s", e)
        return _fallback_narrative(agent_outputs)
    except Exception as e:
        logger.warning("Narrative synthesis LLM failed: %s", e)
        return _fallback_narrative(agent_outputs)

    text = (raw or "").strip()
    if not text:
        return _fallback_narrative(agent_outputs)
    # Strip accidental code fences
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text[:6000]


_MAX_INTERPRETATION_PAYLOAD_CHARS = 100_000

_INTERPRETATION_SYSTEM = """You are a senior intelligence analyst. You receive a structured snapshot of an automated
multi-stream briefing (recap, key findings, scenarios, implications, trends, anomalies, a cross-stream narrative,
and an assessment layer). Your job is to write ONE integrated interpretation of what it all means together.

Requirements:
- Synthesize: explain how the pieces fit, where evidence converges or diverges, and what matters most for posture —
  not a rewrite of the same bullet list.
- If degraded/missing streams are mentioned, explain how that limits confidence.
- English only. Use 3–5 short paragraphs separated by a blank line (double newline). No bullet lists, no markdown
  headings, no JSON.
- Stay under ~550 words. Be direct and analytic; avoid stock phrases and hype."""


def _fallback_briefing_interpretation(payload: Dict[str, Any]) -> str:
    """Short deterministic synthesis when the LLM is unavailable."""
    conflict = str(payload.get("conflict") or "theater").strip() or "theater"
    summary = str(payload.get("summary") or "").strip()
    tl = str(payload.get("threat_level") or "").strip()
    score = payload.get("escalation_score")
    parts: List[str] = []
    lead = f"{conflict}"
    if tl:
        lead += f" — threat level {tl}"
    if isinstance(score, (int, float)):
        lead += f"; composite escalation score ~{float(score):.0f}"
    lead += "."
    parts.append(lead)
    if summary:
        parts.append(summary[:900] + ("…" if len(summary) > 900 else ""))
    kf = payload.get("key_findings") or []
    if isinstance(kf, list) and kf:
        bits = [str(x).strip() for x in kf[:4] if isinstance(x, str) and x.strip()]
        if bits:
            parts.append("Strongest surfaced findings: " + "; ".join(bits) + ".")
    parts.append(
        "Treat this as an automated fuse of OSINT-style signals — corroborate material claims before operational use."
    )
    return "\n\n".join(parts)


def synthesize_briefing_interpretation(
    *,
    conflict: str,
    summary: str,
    threat_level: str,
    escalation_score: float,
    key_findings: List[str],
    scenarios: List[Any],
    implications: List[Dict[str, Any]],
    trends: Dict[str, Any],
    anomalies_rollup: List[Dict[str, Any]],
    narrative_story: str,
    assessment: Dict[str, Any],
    degraded_agents: List[str],
) -> Tuple[str, Dict[str, Any]]:
    """
    Full-briefing interpretive synthesis (Claude Sonnet when LLM_PROVIDER=anthropic and ASSESSMENT_MODEL default;
    otherwise the configured assessment model). Returns (text, small meta dict for the API).
    """
    meta: Dict[str, Any] = {"mode": "fallback", "model": None}

    a_block = assessment.get("assessment") if isinstance(assessment, dict) else None
    if not isinstance(a_block, dict):
        a_block = {}

    scen_compact: List[Dict[str, Any]] = []
    for s in (scenarios or [])[:6]:
        if isinstance(s, dict):
            scen_compact.append(
                {
                    "description": str(s.get("description") or "")[:400],
                    "probability": s.get("probability"),
                }
            )
        elif isinstance(s, str) and s.strip():
            scen_compact.append({"description": s.strip()[:400]})

    impl_compact: List[Dict[str, str]] = []
    for im in (implications or [])[:8]:
        if not isinstance(im, dict):
            continue
        impl_compact.append(
            {
                "title": str(im.get("title") or "")[:200],
                "rationale": str(im.get("rationale") or "")[:400],
            }
        )

    movers = []
    if isinstance(trends, dict):
        tm = trends.get("top_movers")
        if isinstance(tm, list):
            movers = tm[:6]

    anom_compact: List[str] = []
    for a in (anomalies_rollup or [])[:8]:
        if isinstance(a, dict):
            src = str(a.get("source") or "")
            desc = str(a.get("description") or "")
            line = ": ".join(x for x in (src, desc) if x)
            if line:
                anom_compact.append(line[:240])

    payload: Dict[str, Any] = {
        "conflict": conflict,
        "escalation_score": escalation_score,
        "threat_level": threat_level,
        "summary": summary[:3500] if isinstance(summary, str) else "",
        "key_findings": [str(f)[:400] for f in (key_findings or [])[:10] if isinstance(f, str) and f.strip()],
        "scenarios": scen_compact,
        "implications": impl_compact,
        "trends_top_movers": movers,
        "anomalies_rollup": anom_compact,
        "narrative_story": (narrative_story or "")[:4000],
        "assessment_layer": {
            "situation": str(a_block.get("situation") or "")[:1200],
            "significance": str(a_block.get("significance") or "")[:1200],
            "trajectory": a_block.get("trajectory") if isinstance(a_block.get("trajectory"), dict) else {},
        },
        "degraded_agents": list(degraded_agents or [])[:24],
    }

    if (os.getenv("USE_BRIEFING_INTERPRETATION") or "1").strip().lower() in ("0", "false", "no"):
        text = _fallback_briefing_interpretation(payload)
        meta = {**meta, "mode": "disabled_by_env"}
        return text, meta

    try:
        from .llm import LLMCreditExhaustedError, call_llm, get_model_name, require_api_key

        require_api_key()
    except Exception as e:
        logger.debug("Briefing interpretation skipped (no API / key): %s", e)
        return _fallback_briefing_interpretation(payload), meta

    model_env = (os.getenv("BRIEFING_INTERPRETATION_MODEL") or "").strip()
    model = model_env or get_model_name("assessment")
    meta["model"] = model

    user_json = json.dumps(payload, default=str)
    if len(user_json) > _MAX_INTERPRETATION_PAYLOAD_CHARS:
        user_json = user_json[:_MAX_INTERPRETATION_PAYLOAD_CHARS]

    try:
        raw = call_llm(
            system=_INTERPRETATION_SYSTEM,
            user_content=f"BRIEFING_SNAPSHOT_JSON:\n{user_json}",
            model=model,
            temperature=0.3,
            max_tokens=1400,
        )
    except LLMCreditExhaustedError as e:
        logger.error("Briefing interpretation skipped — LLM credits exhausted: %s", e)
        return _fallback_briefing_interpretation(payload), {
            **meta, "mode": "credit_exhausted", "model": model, "error": str(e),
        }
    except Exception as e:
        logger.warning("Briefing interpretation LLM failed: %s", e)
        return _fallback_briefing_interpretation(payload), {
            **meta, "mode": "llm_error", "model": model, "error": str(e),
        }

    text = (raw or "").strip()
    if not text:
        return _fallback_briefing_interpretation(payload), {**meta, "mode": "empty_response", "model": model}
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text[:8000], {"mode": "llm", "model": model}
