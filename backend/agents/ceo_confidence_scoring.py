"""
Finding confidence scoring (3-dimensional) for CEO pipeline.

Purpose: evaluate each (already synthesized) finding across 3 dimensions and
compute an overall confidence (0..1). Used to filter inputs to the assessment step.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .llm import call_llm, get_model_name, require_api_key
from .utils import parse_llm_json

logger = logging.getLogger(__name__)


CONFIDENCE_SCORING_SYSTEM_PROMPT = """You are an intelligence QA reviewer.
You will score each finding across three dimensions and output an overall confidence 0..1.

Dimensions (each 0..1):
1) source_quality: how credible/traceable is it given the provided provenance URLs and streams?
2) corroboration: is it supported by multiple independent streams or signals?
3) specificity: is the claim specific (who/what/where/when) vs vague?

Overall confidence: weighted average:
overall = 0.40*source_quality + 0.35*corroboration + 0.25*specificity

Rules:
- Be conservative: prefer lower scores if evidence is unclear.
- Do NOT invent sources. Use provenance_urls only as grounding context.
- Return ONLY valid JSON, no markdown.

Output schema:
{
  "schema_version": 1,
  "scores": [
    {
      "finding": "<exact input finding string>",
      "dimensions": {"source_quality": 0.0, "corroboration": 0.0, "specificity": 0.0},
      "overall_confidence": 0.0,
      "rationale": "<1-2 sentences>"
    }
  ]
}"""


def _fallback_scores(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Map existing coarse confidence to a reasonable default.
    conf_map = {"high": 0.85, "medium": 0.65, "low": 0.4}
    out_scores = []
    for f in findings[:25]:
        text = str(f.get("finding") or "").strip()
        if not text:
            continue
        c = str(f.get("confidence") or "medium").strip().lower()
        base = conf_map.get(c, 0.65)
        out_scores.append(
            {
                "finding": text,
                "dimensions": {"source_quality": base, "corroboration": base * 0.9, "specificity": base * 0.8},
                "overall_confidence": round(base, 3),
                "rationale": "Fallback confidence derived from coarse confidence labels.",
            }
        )
    return {"schema_version": 1, "scores": out_scores, "_meta": {"mode": "rule_based"}}


def _normalize(parsed: Any, requested_findings: List[str]) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    scores = parsed.get("scores")
    if not isinstance(scores, list):
        return {}

    allowed = set(requested_findings)
    norm: List[Dict[str, Any]] = []
    for item in scores[:40]:
        if not isinstance(item, dict):
            continue
        finding = str(item.get("finding") or "").strip()
        if not finding or finding not in allowed:
            continue
        dims = item.get("dimensions") or {}
        if not isinstance(dims, dict):
            dims = {}

        def _clamp01(x: Any) -> float:
            try:
                v = float(x)
            except (TypeError, ValueError):
                v = 0.0
            return 0.0 if v < 0 else 1.0 if v > 1 else v

        source_quality = _clamp01(dims.get("source_quality"))
        corroboration = _clamp01(dims.get("corroboration"))
        specificity = _clamp01(dims.get("specificity"))
        overall = item.get("overall_confidence")
        overall_f = _clamp01(overall) if overall is not None else _clamp01(
            0.40 * source_quality + 0.35 * corroboration + 0.25 * specificity
        )
        rationale = str(item.get("rationale") or "").strip()[:500]
        norm.append(
            {
                "finding": finding,
                "dimensions": {
                    "source_quality": round(source_quality, 3),
                    "corroboration": round(corroboration, 3),
                    "specificity": round(specificity, 3),
                },
                "overall_confidence": round(overall_f, 3),
                "rationale": rationale,
            }
        )

    # Ensure we have entries for everything requested (deterministic fill).
    seen = {s["finding"] for s in norm if isinstance(s, dict) and s.get("finding")}
    for f in requested_findings:
        if f in seen:
            continue
        norm.append(
            {
                "finding": f,
                "dimensions": {"source_quality": 0.5, "corroboration": 0.4, "specificity": 0.4},
                "overall_confidence": 0.45,
                "rationale": "Defaulted due to missing score from model output.",
            }
        )

    return {"schema_version": 1, "scores": norm[: len(requested_findings)]}


def score_findings_confidence(
    *,
    conflict: str,
    findings: List[Dict[str, Any]],
    provenance_urls: Optional[List[str]] = None,
    stakeholder: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Score synthesized findings with a cheap model (default: Haiku).

    findings: list of {"finding": str, "confidence": "high|medium|low", "context": str?}
    """
    requested = [str(f.get("finding") or "").strip() for f in findings if isinstance(f, dict)]
    requested = [r for r in requested if r]
    if not requested:
        return {"schema_version": 1, "scores": [], "_meta": {"mode": "disabled", "reason": "no_findings"}}

    user_payload = {
        "conflict": conflict,
        "stakeholder": stakeholder or {},
        "provenance_urls": (provenance_urls or [])[:25],
        "findings": [
            {"finding": str(f.get("finding") or ""), "confidence": str(f.get("confidence") or ""), "context": f.get("context") or ""}
            for f in findings[:25]
            if isinstance(f, dict) and f.get("finding")
        ],
    }

    tried_model = None
    try:
        require_api_key()
        import json

        model = get_model_name("confidence_scoring")
        tried_model = model
        raw = call_llm(
            system=CONFIDENCE_SCORING_SYSTEM_PROMPT,
            user_content=json.dumps(user_payload, default=str)[:200_000],
            model=model,
            temperature=0.1,
            max_tokens=2500,
        )
        parsed = parse_llm_json(raw) if raw else None
        norm = _normalize(parsed, requested)
        if norm.get("scores"):
            norm["_meta"] = {"mode": "llm", "model": model}
            return norm
    except Exception as e:
        logger.warning("CEO confidence scoring failed (model=%s): %s", tried_model, e)

    fb = _fallback_scores(findings)
    fb["_meta"] = {"mode": "rule_based", "reason": "llm_unavailable_or_invalid"}
    return fb

