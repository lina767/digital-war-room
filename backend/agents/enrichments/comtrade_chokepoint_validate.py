"""
Comtrade chokepoint validation enrichment.

Purpose:
- When CHOKEPOINT indicates disruption at Hormuz/Bab el-Mandeb, attach a compact
  Comtrade-based exposure/validation block (energy-only) for CEO/FININT to cite.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional, Tuple

from agents.fetchers.comtrade_fetchers import preview_energy_trade_flows, summarize_trade_records
from agents.utils import ProcessingStep, ScoreConfidence, SourceResult, build_agent_meta, utc_now_iso


HS_ENERGY_CODES = ["2709", "2710"]

# Minimal initial mapping. Keep explicit and auditable.
CHOKEPOINT_TO_EXPORTERS = {
    "Strait of Hormuz": ["682", "784", "368", "414", "634", "512", "364"],  # SA, AE, IQ, KW, QA, OM, IR
    "Bab el-Mandeb": ["682", "784", "368", "414", "634", "512", "364"],
}

# Major importers (energy demand centers); codes are UN M49/Comtrade numeric.
DEFAULT_IMPORTERS = ["156", "356", "392", "410"]  # CN, IN, JP, KR


def _last_complete_month_yyyymm(now: Optional[dt.datetime] = None) -> str:
    n = now or dt.datetime.utcnow()
    first = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = first - dt.timedelta(days=1)
    return f"{last_month.year:04d}{last_month.month:02d}"


def _extract_triggered_chokepoints(chokepoint_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    cps = chokepoint_result.get("chokepoints") if isinstance(chokepoint_result, dict) else None
    out: List[Dict[str, Any]] = []
    if not isinstance(cps, list):
        return out
    for cp in cps:
        if not isinstance(cp, dict):
            continue
        name = str(cp.get("name") or "").strip()
        if name not in ("Strait of Hormuz", "Bab el-Mandeb"):
            continue
        status = str(cp.get("status") or "").strip().upper()
        risk = cp.get("disruption_risk")
        try:
            risk_f = float(risk) if risk is not None else None
        except (TypeError, ValueError):
            risk_f = None

        # Trigger on status OR risk.
        triggered = status in ("RESTRICTED", "CONTESTED", "DISRUPTED") or (isinstance(risk_f, float) and risk_f >= 40)
        if not triggered:
            continue
        out.append({"name": name, "status": status or "OPEN", "disruption_risk": risk_f})
    return out


def _compute_validation_score(
    *,
    triggered_chokepoints: List[Dict[str, Any]],
    total_value_usd: float,
    ok_calls: int,
    attempted_calls: int,
) -> float:
    """
    Heuristic 0..100: higher when (a) chokepoint risk is high and (b) trade value is non-trivial.
    Keyless preview yields sparse values; we still produce a stable score.
    """
    base = 0.0
    if triggered_chokepoints:
        max_risk = 0.0
        for cp in triggered_chokepoints:
            r = cp.get("disruption_risk")
            if isinstance(r, (int, float)):
                max_risk = max(max_risk, float(r))
        base = min(75.0, max_risk)  # cap signal so it doesn't dominate overall CEO score

    # Scale trade values (USD) into 0..25 boost. This is intentionally conservative.
    #  - 0 → 0
    #  - 50M → ~10
    #  - 200M → ~18
    #  - 1B+ → 25
    boost = 0.0
    try:
        v = float(total_value_usd or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    if v > 0:
        if v >= 1_000_000_000:
            boost = 25.0
        elif v >= 200_000_000:
            boost = 18.0
        elif v >= 50_000_000:
            boost = 10.0
        else:
            boost = 5.0

    # Data quality penalty when preview calls fail.
    quality = 1.0
    if attempted_calls > 0:
        ratio = ok_calls / max(1, attempted_calls)
        quality = 0.6 + 0.4 * ratio  # 0.6..1.0

    return round(min(100.0, (base + boost) * quality), 1)


def run_comtrade_chokepoint_validation(
    *,
    conflict: str,
    finint_result: Dict[str, Any],
    chokepoint_result: Dict[str, Any],
) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()

    triggered = _extract_triggered_chokepoints(chokepoint_result)
    if not triggered:
        duration_ms = int((time.perf_counter() - start) * 1000)
        out = {
            "triggered": False,
            "summary": "COMTRADE: not triggered (no elevated Hormuz/Bab el-Mandeb disruption signal).",
            "validation_score": 0.0,
            "hs_codes": HS_ENERGY_CODES,
            "period": _last_complete_month_yyyymm(),
            "chokepoints": [],
            "top_flows": [],
            "fetched_at": fetched_at,
        }
        out["_meta"] = build_agent_meta(
            "comtrade_chokepoint_validate",
            fetched_at,
            duration_ms,
            [SourceResult(name="UN Comtrade (preview)", status="degraded", fetched_at=fetched_at)],
            has_any_data=False,
            confidence=ScoreConfidence(level="low", sources_ok=[], sources_missing=["chokepoint_trigger"]),
            processing_steps=[ProcessingStep(step="check_chokepoint_trigger", at=fetched_at)],
        )
        return out

    period = _last_complete_month_yyyymm()

    # Determine which chokepoints to query.
    cp_names = [cp["name"] for cp in triggered if isinstance(cp, dict) and cp.get("name")]
    exporters: List[str] = []
    for cp in cp_names:
        exporters.extend(CHOKEPOINT_TO_EXPORTERS.get(cp, []))
    exporters = list(dict.fromkeys([e for e in exporters if isinstance(e, str) and e.strip()]))[:10]
    partners = DEFAULT_IMPORTERS

    attempted = 0
    ok_calls = 0
    all_records: List[Dict[str, Any]] = []
    raw_calls: List[Dict[str, Any]] = []

    for hs in HS_ENERGY_CODES:
        for rep in exporters:
            for p in partners:
                attempted += 1
                resp = preview_energy_trade_flows(
                    period=period,
                    reporterCode=rep,
                    partnerCode=p,
                    cmdCode=hs,
                    flowCode="X",
                )
                raw_calls.append({"hs": hs, "reporterCode": rep, "partnerCode": p, "ok": resp.get("ok"), "error": resp.get("error")})
                if resp.get("ok"):
                    ok_calls += 1
                recs = resp.get("records")
                if isinstance(recs, list):
                    all_records.extend([r for r in recs if isinstance(r, dict)])
                # Keep preview usage light.
                if attempted >= 24:
                    break
            if attempted >= 24:
                break
        if attempted >= 24:
            break

    summary_stats = summarize_trade_records(all_records, top_n=6)
    total_value = 0.0
    if isinstance(summary_stats.get("total_value"), (int, float)):
        total_value = float(summary_stats["total_value"])

    validation_score = _compute_validation_score(
        triggered_chokepoints=triggered,
        total_value_usd=total_value,
        ok_calls=ok_calls,
        attempted_calls=attempted,
    )

    top_flows = summary_stats.get("top_flows") if isinstance(summary_stats.get("top_flows"), list) else []
    top_flows = [x for x in top_flows if isinstance(x, dict)][:8]

    # Compact text for synthesis to cite.
    cp_part = "; ".join(
        [
            f"{cp.get('name')} {cp.get('status')} (risk {cp.get('disruption_risk'):.0f})"
            if isinstance(cp.get("disruption_risk"), (int, float))
            else f"{cp.get('name')} {cp.get('status')}"
            for cp in triggered
        ][:3]
    )
    flow_part = ", ".join(
        [f"{f.get('reporter')}→{f.get('partner')} ${float(f.get('value') or 0):.0f}" for f in top_flows[:3]]
    )
    summary = f"COMTRADE: triggered by {cp_part}. Preview energy flows (HS 2709/2710, {period}) suggest exposure via top flows: {flow_part}."

    duration_ms = int((time.perf_counter() - start) * 1000)
    sources_ok = ["UN Comtrade preview"] if ok_calls > 0 else []
    sources_missing = [] if ok_calls > 0 else ["UN Comtrade preview"]
    confidence_level = "medium" if ok_calls >= 4 else "low"
    score_conf = ScoreConfidence(level=confidence_level, sources_ok=sources_ok, sources_missing=sources_missing)

    out = {
        "triggered": True,
        "chokepoints": triggered,
        "hs_codes": HS_ENERGY_CODES,
        "period": period,
        "reporters": exporters,
        "partners": partners,
        "attempted_calls": attempted,
        "ok_calls": ok_calls,
        "validation_score": validation_score,
        "top_flows": top_flows,
        "summary_stats": {
            "total_value": summary_stats.get("total_value"),
        },
        "summary": summary[:900],
        "key_findings": [
            f"Chokepoint disruption signal: {cp_part}"[:240],
            f"Comtrade preview energy exposure (HS 2709/2710, {period}): {flow_part}"[:240] if flow_part else f"Comtrade preview attempted {attempted} calls; ok {ok_calls}"[:240],
        ],
        "fetched_at": fetched_at,
        "debug": {"raw_calls": raw_calls[:30]},
    }
    out["_meta"] = build_agent_meta(
        "comtrade_chokepoint_validate",
        fetched_at,
        duration_ms,
        [
            SourceResult(
                name="UN Comtrade (preview)",
                status="ok" if ok_calls > 0 else "error",
                fetched_at=fetched_at,
                record_count=len(all_records),
            )
        ],
        has_any_data=bool(all_records),
        confidence=score_conf,
        processing_steps=[
            ProcessingStep(step="check_chokepoint_trigger", at=fetched_at),
            ProcessingStep(step="fetch_comtrade_preview", at=fetched_at),
            ProcessingStep(step="summarize_exposure", at=fetched_at),
        ],
    )
    return out

