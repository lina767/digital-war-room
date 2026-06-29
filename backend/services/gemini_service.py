"""Research LLM client (formerly Gemini) — now backed by Anthropic/OpenAI.

The original Gemini integration was removed to avoid Google API costs. To
minimise churn, this module keeps the public surface used by callers:
  - ``run_gemini_research`` / ``run_gemini_text`` / ``run_gemini_vision_json``
  - ``GeminiResearchResponse`` / ``GeminiTextResponse`` / ``GeminiVisionResponse``
  - ``default_research_budget`` / ``evaluate_budget`` / ``estimate_cost_usd``

Internally everything routes through ``agents.llm`` so the existing
``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` credentials are reused.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from agents.llm import LLMCreditExhaustedError, call_llm, get_model_name
from agents.research_contracts import ResearchBudgetStatus, ResearchRunBudget, ResearchUsage

logger = logging.getLogger(__name__)

# Claude Haiku 4.5 pricing (USD per 1M tokens); overridable via env for Sonnet/OpenAI.
RESEARCH_INPUT_USD_PER_MTOK = float(os.getenv("RESEARCH_INPUT_USD_PER_MTOK", "1.0"))
RESEARCH_OUTPUT_USD_PER_MTOK = float(os.getenv("RESEARCH_OUTPUT_USD_PER_MTOK", "5.0"))

RESEARCH_MAX_REQUESTS_PER_RUN = int(os.getenv("RESEARCH_MAX_REQUESTS_PER_RUN", "1"))
RESEARCH_MAX_INPUT_TOKENS_PER_RUN = int(os.getenv("RESEARCH_MAX_INPUT_TOKENS_PER_RUN", "12000"))
RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN = int(os.getenv("RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN", "3000"))
RESEARCH_MAX_COST_USD_PER_RUN = float(os.getenv("RESEARCH_MAX_COST_USD_PER_RUN", "0.08"))

# Crude fallback token estimator when the provider SDK does not surface usage.
_FALLBACK_CHARS_PER_TOKEN = 4.0


def default_research_budget() -> ResearchRunBudget:
    return ResearchRunBudget(
        max_requests_per_run=RESEARCH_MAX_REQUESTS_PER_RUN,
        max_input_tokens_per_run=RESEARCH_MAX_INPUT_TOKENS_PER_RUN,
        max_output_tokens_per_run=RESEARCH_MAX_OUTPUT_TOKENS_PER_RUN,
        max_cost_usd_per_run=RESEARCH_MAX_COST_USD_PER_RUN,
    )


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (float(input_tokens) / 1_000_000.0) * RESEARCH_INPUT_USD_PER_MTOK + (
        float(output_tokens) / 1_000_000.0
    ) * RESEARCH_OUTPUT_USD_PER_MTOK


def evaluate_budget(usage: ResearchUsage, budget: ResearchRunBudget) -> ResearchBudgetStatus:
    blocked_reason: Optional[str] = None
    if usage.requests >= budget.max_requests_per_run:
        blocked_reason = "max_requests_per_run_exceeded"
    elif budget.max_input_tokens_per_run > 0 and usage.input_tokens >= budget.max_input_tokens_per_run:
        blocked_reason = "max_input_tokens_per_run_exceeded"
    elif budget.max_output_tokens_per_run > 0 and usage.output_tokens >= budget.max_output_tokens_per_run:
        blocked_reason = "max_output_tokens_per_run_exceeded"
    elif budget.max_cost_usd_per_run > 0 and usage.estimated_cost_usd >= budget.max_cost_usd_per_run:
        blocked_reason = "max_cost_usd_per_run_exceeded"
    return ResearchBudgetStatus(allowed=blocked_reason is None, blocked_reason=blocked_reason, budget=budget, usage=usage)


# Legacy dataclass names are preserved so callers stay unchanged.


@dataclass
class GeminiResearchResponse:
    ok: bool
    raw_text: str
    parsed_json: Optional[Dict[str, Any]]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None


@dataclass
class GeminiTextResponse:
    ok: bool
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None


@dataclass
class GeminiVisionResponse:
    ok: bool
    parsed_json: Optional[Dict[str, Any]]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None


def _approx_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / _FALLBACK_CHARS_PER_TOKEN))


def _llm_provider_ready() -> Optional[str]:
    if (os.getenv("LLM_PROVIDER") or "").strip().lower() == "openai":
        if os.getenv("OPENAI_API_KEY"):
            return None
        return "missing_openai_api_key"
    if os.getenv("ANTHROPIC_API_KEY"):
        return None
    if os.getenv("OPENAI_API_KEY"):
        return None
    return "missing_llm_api_key"


def _parse_json_text(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


_RESEARCH_SYSTEM = (
    "You are a strict OSINT research assistant. You always reply with valid JSON "
    "when the user asks for a JSON object; otherwise keep answers short and factual."
)

_TEXT_SYSTEM = (
    "You are a concise intelligence analyst. Respond with a few well-calibrated "
    "English sentences. Use only the data provided and never invent facts."
)


def run_gemini_research(prompt: str) -> GeminiResearchResponse:
    """Structured-JSON research call. Name kept for call-site compatibility."""
    missing = _llm_provider_ready()
    if missing:
        return GeminiResearchResponse(
            ok=False,
            raw_text="",
            parsed_json=None,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            error=missing,
        )
    try:
        text = call_llm(
            system=_RESEARCH_SYSTEM,
            user_content=prompt,
            model=get_model_name("agent"),
            temperature=0.0,
            max_tokens=3000,
        )
    except LLMCreditExhaustedError as exc:
        logger.warning("Research LLM credit exhausted: %s", exc)
        return GeminiResearchResponse(
            ok=False, raw_text="", parsed_json=None, input_tokens=0, output_tokens=0,
            cost_usd=0.0, error="credit_exhausted",
        )
    except Exception as exc:
        logger.warning("Research LLM call failed: %s", exc)
        return GeminiResearchResponse(
            ok=False, raw_text="", parsed_json=None, input_tokens=0, output_tokens=0,
            cost_usd=0.0, error=f"request_failed:{type(exc).__name__}",
        )

    parsed = _parse_json_text(text)
    input_tokens = _approx_token_count(prompt)
    output_tokens = _approx_token_count(text or "")
    cost = estimate_cost_usd(input_tokens, output_tokens)
    return GeminiResearchResponse(
        ok=True,
        raw_text=text or "",
        parsed_json=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if parsed is not None else "invalid_json_response",
    )


def run_gemini_text(prompt: str) -> GeminiTextResponse:
    """Plain-text call (e.g. SIGINT brief assessment)."""
    missing = _llm_provider_ready()
    if missing:
        return GeminiTextResponse(
            ok=False, text="", input_tokens=0, output_tokens=0, cost_usd=0.0, error=missing,
        )
    try:
        text = call_llm(
            system=_TEXT_SYSTEM,
            user_content=prompt,
            model=get_model_name("agent"),
            temperature=0.1,
            max_tokens=600,
        )
    except LLMCreditExhaustedError as exc:
        logger.warning("Research LLM credit exhausted: %s", exc)
        return GeminiTextResponse(
            ok=False, text="", input_tokens=0, output_tokens=0, cost_usd=0.0,
            error="credit_exhausted",
        )
    except Exception as exc:
        logger.warning("Research LLM text call failed: %s", exc)
        return GeminiTextResponse(
            ok=False, text="", input_tokens=0, output_tokens=0, cost_usd=0.0,
            error=f"request_failed:{type(exc).__name__}",
        )

    text = (text or "").strip()
    input_tokens = _approx_token_count(prompt)
    output_tokens = _approx_token_count(text)
    cost = estimate_cost_usd(input_tokens, output_tokens)
    return GeminiTextResponse(
        ok=bool(text),
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if text else "empty_text_response",
    )


def run_gemini_vision_json(prompt: str, image_bytes: bytes, mime_type: str = "image/png") -> GeminiVisionResponse:
    """Multimodal (prompt + image) call that returns JSON.

    Uses Anthropic Claude vision (Haiku supports images). Returns an unavailable
    response if no ``ANTHROPIC_API_KEY`` is configured or the image is missing.
    """
    if not image_bytes:
        return GeminiVisionResponse(
            ok=False, parsed_json=None, input_tokens=0, output_tokens=0, cost_usd=0.0,
            error="missing_image_bytes",
        )
    if not os.getenv("ANTHROPIC_API_KEY"):
        return GeminiVisionResponse(
            ok=False, parsed_json=None, input_tokens=0, output_tokens=0, cost_usd=0.0,
            error="vision_unavailable_no_anthropic_key",
        )

    try:
        from anthropic import Anthropic
    except Exception as exc:
        return GeminiVisionResponse(
            ok=False, parsed_json=None, input_tokens=0, output_tokens=0, cost_usd=0.0,
            error=f"anthropic_import_failed:{type(exc).__name__}",
        )

    encoded = base64.b64encode(image_bytes).decode("ascii")
    model = os.getenv("VISION_MODEL") or get_model_name("agent")
    try:
        client = Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=1200,
            temperature=0,
            system=_RESEARCH_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime_type, "data": encoded},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except Exception as exc:
        logger.warning("Vision LLM call failed: %s", exc)
        return GeminiVisionResponse(
            ok=False, parsed_json=None, input_tokens=0, output_tokens=0, cost_usd=0.0,
            error=f"request_failed:{type(exc).__name__}",
        )

    text_parts = []
    for block in getattr(resp, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", "") or "")
    text = "\n".join(text_parts).strip()
    parsed = _parse_json_text(text)

    try:
        input_tokens = int(getattr(resp.usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(resp.usage, "output_tokens", 0) or 0)
    except Exception:
        input_tokens = _approx_token_count(prompt)
        output_tokens = _approx_token_count(text)
    cost = estimate_cost_usd(input_tokens, output_tokens)

    return GeminiVisionResponse(
        ok=parsed is not None,
        parsed_json=parsed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        error=None if parsed is not None else "invalid_json_response",
    )
