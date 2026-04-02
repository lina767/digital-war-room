"""
UN Comtrade fetchers (thin wrappers).

Design goals:
- Always return a small JSON-serializable dict (never pandas objects).
- Keyless-first: use preview endpoints when subscription key is absent.
- Fail soft: on any error, return {"error": "..."} plus timing metadata.
- Keep payload sizes small (trim records).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agents.utils import utc_now_iso

# Simple in-process TTL cache (best-effort).
_CACHE: Dict[Tuple[str, ...], Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_S = 6 * 3600


def _cache_get(key: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    row = _CACHE.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.time() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: Tuple[str, ...], payload: Dict[str, Any]) -> None:
    _CACHE[key] = (time.time() + _CACHE_TTL_S, payload)


def _to_records(df_or_obj: Any, *, max_records: int = 80) -> List[Dict[str, Any]]:
    """
    comtradeapicall returns a pandas DataFrame in most code paths.
    Normalize to list[dict] and trim.
    """
    try:
        # Pandas DataFrame
        if hasattr(df_or_obj, "to_dict"):
            rows = df_or_obj.to_dict(orient="records")  # type: ignore[no-any-return]
            if isinstance(rows, list):
                out = [r for r in rows if isinstance(r, dict)]
                return out[:max_records]
    except Exception:
        pass
    return []


def preview_energy_trade_flows(
    *,
    typeCode: str = "C",
    freqCode: str = "M",
    clCode: str = "HS",
    period: str,
    reporterCode: str,
    partnerCode: Optional[str],
    cmdCode: str,
    flowCode: str = "X",
    maxRecords: int = 500,
    breakdownMode: str = "classic",
    includeDesc: bool = True,
    cache_ttl_s: int = _CACHE_TTL_S,
) -> Dict[str, Any]:
    """
    Keyless preview using comtradeapicall.previewFinalData.

    Returns:
      {
        "ok": bool,
        "fetched_at": "...",
        "criteria": {...},
        "records": [...],
        "record_count": int,
        "error": "...?" (optional)
      }
    """
    fetched_at = utc_now_iso()
    start = time.perf_counter()

    cache_key = (
        "previewFinalData",
        str(typeCode),
        str(freqCode),
        str(clCode),
        str(period),
        str(reporterCode),
        str(partnerCode) if partnerCode is not None else "",
        str(cmdCode),
        str(flowCode),
        str(maxRecords),
        str(breakdownMode),
        "1" if includeDesc else "0",
        str(int(cache_ttl_s)),
    )

    if cache_ttl_s and cache_ttl_s > 0:
        cached = _cache_get(cache_key)
        if cached is not None:
            # mark cached but keep schema stable
            out = dict(cached)
            out["cache"] = {"hit": True, "ttl_s": cache_ttl_s}
            return out

    try:
        import comtradeapicall  # type: ignore

        df = comtradeapicall.previewFinalData(
            typeCode=typeCode,
            freqCode=freqCode,
            clCode=clCode,
            period=period,
            reporterCode=reporterCode,
            cmdCode=cmdCode,
            flowCode=flowCode,
            partnerCode=partnerCode,
            partner2Code=None,
            customsCode=None,
            motCode=None,
            maxRecords=maxRecords,
            format_output="JSON",
            aggregateBy=None,
            breakdownMode=breakdownMode,
            countOnly=None,
            includeDesc=includeDesc,
        )
        records = _to_records(df, max_records=80)
        out: Dict[str, Any] = {
            "ok": True,
            "fetched_at": fetched_at,
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "criteria": {
                "typeCode": typeCode,
                "freqCode": freqCode,
                "clCode": clCode,
                "period": period,
                "reporterCode": reporterCode,
                "partnerCode": partnerCode,
                "cmdCode": cmdCode,
                "flowCode": flowCode,
                "breakdownMode": breakdownMode,
                "includeDesc": includeDesc,
                "maxRecords": maxRecords,
            },
            "records": records,
            "record_count": len(records),
        }
        if cache_ttl_s and cache_ttl_s > 0:
            to_cache = dict(out)
            to_cache["cache"] = {"hit": False, "ttl_s": cache_ttl_s}
            _cache_set(cache_key, to_cache)
            out["cache"] = {"hit": False, "ttl_s": cache_ttl_s}
        return out
    except Exception as e:
        out = {
            "ok": False,
            "fetched_at": fetched_at,
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "criteria": {
                "typeCode": typeCode,
                "freqCode": freqCode,
                "clCode": clCode,
                "period": period,
                "reporterCode": reporterCode,
                "partnerCode": partnerCode,
                "cmdCode": cmdCode,
                "flowCode": flowCode,
            },
            "records": [],
            "record_count": 0,
            "error": str(e),
        }
        if cache_ttl_s and cache_ttl_s > 0:
            out["cache"] = {"hit": False, "ttl_s": cache_ttl_s}
        return out


def summarize_trade_records(
    records: Iterable[Dict[str, Any]],
    *,
    value_keys: Optional[List[str]] = None,
    top_n: int = 6,
) -> Dict[str, Any]:
    """
    Summarize Comtrade-like records by reporter/partner with best-effort field probing.
    This avoids hard-binding to a specific Comtrade response schema.
    """
    value_keys = value_keys or ["TradeValue", "tradeValue", "primaryValue", "primaryValue"]
    agg: Dict[Tuple[str, str], float] = {}
    samples: List[Dict[str, Any]] = []

    for r in records:
        if not isinstance(r, dict):
            continue
        reporter = str(r.get("reporterISO") or r.get("ReporterISO") or r.get("reporterDesc") or r.get("rtTitle") or r.get("rt3ISO") or r.get("rtCode") or "").strip()
        partner = str(r.get("partnerISO") or r.get("PartnerISO") or r.get("partnerDesc") or r.get("ptTitle") or r.get("pt3ISO") or r.get("ptCode") or "").strip()
        if not reporter:
            reporter = str(r.get("rtCode") or r.get("reporterCode") or "").strip()
        if not partner:
            partner = str(r.get("ptCode") or r.get("partnerCode") or "").strip()

        val: Optional[float] = None
        for k in value_keys:
            if k in r:
                try:
                    val = float(r.get(k))  # type: ignore[arg-type]
                    break
                except (TypeError, ValueError):
                    continue
        if val is None:
            continue
        key = (reporter or "unknown", partner or "unknown")
        agg[key] = agg.get(key, 0.0) + val
        if len(samples) < 10:
            samples.append({k: r.get(k) for k in ("period", "cmdCode", "cmdDesc", "reporterDesc", "partnerDesc", "TradeValue", "tradeValue")})

    top = sorted(agg.items(), key=lambda x: x[1], reverse=True)[: max(1, top_n)]
    top_flows = [{"reporter": a, "partner": b, "value": round(v, 2)} for (a, b), v in top]

    total = sum(agg.values()) if agg else 0.0
    return {"total_value": round(total, 2), "top_flows": top_flows, "sample_rows": samples}

