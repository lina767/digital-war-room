"""
Sanctions compliance routes: sanctions-check, zones, threshold, document-qa, route-screening, risk-score.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.config import DEFAULT_CONFLICT
from middleware.rate_limit import limiter
from compliance.risk_score import compute_compliance_risk
from compliance.sanctions_search import get_threshold_policy, search_sanctions
from compliance.supply_chain import get_intermediary_policy, screen_route
from compliance.zones import ALL_ZONES, SANCTIONS_ZONES

router = APIRouter()


class SanctionsCheckRequest(BaseModel):
    query: Optional[str] = None
    queries: Optional[List[str]] = None
    include_ownership_chains: bool = False


def _screened_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.post("/compliance/sanctions-check")
@limiter.limit("30/minute")
async def sanctions_check(request: Request, body: SanctionsCheckRequest) -> Any:
    """
    POST /api/compliance/sanctions-check
    Screen one or more names against OFAC SDN (and later EU/UN) sanctions lists.
    Single: body.query. Batch: body.queries (max 5 concurrent). Returns screened_at per result.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    import asyncio

    disclaimer = (
        "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review."
    )
    try:
        if body.queries:
            sem = asyncio.Semaphore(5)

            async def one(q: str) -> Dict[str, Any]:
                async with sem:
                    matches = await search_sanctions(
                        q,
                        include_ownership_chains=body.include_ownership_chains,
                    )
                    return {"query": q, "matches": matches, "screened_at": _screened_at_iso()}

            tasks = [one(q.strip()) for q in body.queries if q and str(q).strip()]
            results: List[Dict[str, Any] | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)
            out: List[Dict[str, Any]] = []
            for r in results:
                if isinstance(r, BaseException):
                    out.append({"query": "", "matches": [], "screened_at": _screened_at_iso(), "error": str(r)})
                else:
                    out.append(r)
            return {"results": out, "threshold_policy": get_threshold_policy(), "disclaimer": disclaimer}
        q = (body.query or "").strip()
        if not q:
            return JSONResponse(status_code=400, content={"error": "query or queries required"})
        results = await search_sanctions(
            q,
            include_ownership_chains=body.include_ownership_chains,
        )
        return {
            "query": q,
            "matches": results,
            "screened_at": _screened_at_iso(),
            "threshold_policy": get_threshold_policy(),
            "disclaimer": disclaimer,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/compliance/zones")
async def get_compliance_zones() -> Dict[str, List[Dict[str, Any]]]:
    """
    GET /api/compliance/zones
    Returns all configured sanctions and conflict zones (bounding boxes).
    """
    return {
        "sanctions_zones": [z.to_dict() for z in SANCTIONS_ZONES],
        "all_zones": [z.to_dict() for z in ALL_ZONES],
    }


@router.get("/compliance/threshold-policy")
async def get_compliance_threshold_policy() -> Any:
    """
    GET /api/compliance/threshold-policy
    Returns the current fuzzy matching threshold policy for transparency.
    """
    return get_threshold_policy()


class ComplianceDocumentQAContext(BaseModel):
    """Optional compliance context sent from the frontend (current panel state)."""

    ofac_sample: Optional[List[str]] = None
    ofac_programs_summary: Optional[str] = None
    risk_level: Optional[str] = None
    risk_drivers_summary: Optional[str] = None


class ComplianceDocumentQARequest(BaseModel):
    """Request for Document QA using compliance context only (no PDF ingest)."""

    question: str
    conflict: Optional[str] = None
    context: Optional[ComplianceDocumentQAContext] = None


def _build_compliance_context(conflict: str, ctx: Optional[ComplianceDocumentQAContext]) -> str:
    """Build a single text block from conflict + context for the LLM."""
    parts = [f"Conflict / region: {conflict or 'Not specified'}."]
    if ctx:
        if ctx.risk_level:
            parts.append(f"Current compliance risk level: {ctx.risk_level}.")
        if ctx.risk_drivers_summary:
            parts.append(f"Risk drivers: {ctx.risk_drivers_summary}")
        if ctx.ofac_sample:
            names = ", ".join(ctx.ofac_sample[:20])
            parts.append(f"OFAC SDN sample entities (from current run): {names}.")
        if ctx.ofac_programs_summary:
            parts.append(f"OFAC programs (name, count): {ctx.ofac_programs_summary}")
    return "\n".join(parts)


@router.post("/compliance/document-qa")
@limiter.limit("20/minute")
async def compliance_document_qa(request: Request, body: ComplianceDocumentQARequest) -> Any:
    """
    POST /api/compliance/document-qa
    Answer a question using the current compliance context (no PDF/RAG).
    Context: conflict, risk level, risk drivers, OFAC sample, recent actions.
    Uses Haiku; answer is based only on the provided context.
    """
    try:
        from services.haiku_service import document_qa as haiku_document_qa

        if not (body.question or "").strip():
            return JSONResponse(status_code=400, content={"error": "question is required"})

        conflict = (body.conflict or "").strip() or DEFAULT_CONFLICT
        context_str = _build_compliance_context(conflict, body.context)
        if not context_str.strip():
            context_str = "No compliance context provided."

        result = await haiku_document_qa(
            body.question.strip(),
            [context_str],
            max_chunks=1,
        )
        if not result:
            return {
                "answer": "The service could not process your question at this time.",
                "confidence": 0,
                "sources": [],
                "disclaimer": (
                    "Intelligence signals only – not legal advice. "
                    "Supports due diligence but does not replace legal review."
                ),
            }
        result["disclaimer"] = (
            "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review."
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class RouteScreeningWaypoint(BaseModel):
    label: str
    lat: float
    lon: float
    country_code: str = ""
    port_type: str = "port"


class RouteScreeningRequest(BaseModel):
    route_label: str
    waypoints: List[RouteScreeningWaypoint]


@router.post("/compliance/route-screening")
@limiter.limit("30/minute")
async def route_screening(request: Request, body: RouteScreeningRequest) -> Any:
    """
    POST /api/compliance/route-screening
    Screen a trade route against sanctions zones and intermediary policy.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    try:
        wps = [w.model_dump() for w in body.waypoints]
        result = screen_route(body.route_label, wps)
        return {
            **result,
            "disclaimer": (
                "Intelligence signals only – not legal advice. "
                "Supports due diligence but does not replace legal review."
            ),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/compliance/intermediary-policy")
async def get_intermediary_policy_route() -> Dict[str, Any]:
    """
    GET /api/compliance/intermediary-policy
    Returns the active intermediary (middlemen) policy for transparency and audit.
    """
    return {
        "policy": get_intermediary_policy(),
        "note": (
            "This policy defines which transit hubs are flagged for review. "
            "It is configurable and documented; no country is automatically blocked."
        ),
    }


class RiskScoreRequest(BaseModel):
    sanctions_matches: Optional[List[Dict[str, Any]]] = None
    geofencing_alerts: Optional[List[Dict[str, Any]]] = None
    supply_chain_result: Optional[Dict[str, Any]] = None
    ais_anomalies: Optional[List[Dict[str, Any]]] = None
    escalation_level: Optional[str] = None


@router.post("/compliance/risk-score")
@limiter.limit("60/minute")
async def compliance_risk_score(request: Request, body: RiskScoreRequest) -> Any:
    """
    POST /api/compliance/risk-score
    Compute compliance risk score from provided signals.

    DISCLAIMER: Intelligence signals only – not legal advice.
    """
    try:
        result = compute_compliance_risk(
            sanctions_matches=body.sanctions_matches,
            geofencing_alerts=body.geofencing_alerts,
            supply_chain_result=body.supply_chain_result,
            ais_anomalies=body.ais_anomalies,
            escalation_level=body.escalation_level,
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
