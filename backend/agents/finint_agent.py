import asyncio
import os
from typing import Any, Dict, List, Tuple

import httpx


ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
POLYMARKET_MARKETS_URL = "https://gamma-api.polymarket.com/markets"

POLYMARKET_KEYWORDS = [
    "iran",
    "israel",
    "gaza",
    "hezbollah",
    "hamas",
    "nuclear deal",
    "middle east war",
    "us attack",
    "airstrike",
    "irgc",
    "oil embargo",
    "strait of hormuz",
    "persian gulf conflict",
]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


async def _fetch_alpha_series(client: httpx.AsyncClient, function: str, api_key: str) -> Dict[str, Any]:
    params = {
        "function": function,
        "interval": "daily",
        "apikey": api_key,
    }
    resp = await client.get(ALPHAVANTAGE_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def _parse_alpha_series(data: Dict[str, Any]) -> Tuple[str, float | None, float | None]:
    """
    Parse Alpha Vantage commodities payload.

    Returns (as_of_date, latest_price, pct_change_vs_prev_day).
    """
    series = data.get("data")
    if not isinstance(series, list) or len(series) == 0:
        return "", None, None

    latest = series[0]
    prev = series[1] if len(series) > 1 else None

    as_of = str(latest.get("date") or latest.get("timestamp") or "")
    latest_price = _safe_float(latest.get("value") or latest.get("price"))
    prev_price = _safe_float(prev.get("value") or prev.get("price")) if prev else None

    change_pct: float | None = None
    if latest_price is not None and prev_price not in (None, 0):
        change_pct = (latest_price - prev_price) / prev_price * 100.0

    return as_of, latest_price, change_pct


async def _fetch_polymarket_markets(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    resp = await client.get(POLYMARKET_MARKETS_URL, params={"limit": 100})
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("markets"), list):
        return data["markets"]
    return []


def _market_matches_keywords(question: str) -> bool:
    q_lower = question.lower()
    return any(keyword in q_lower for keyword in POLYMARKET_KEYWORDS)


def _extract_probability(market: Dict[str, Any]) -> float:
    prices = market.get("outcomePrices") or market.get("prices") or []
    if not isinstance(prices, list):
        prices = [prices]

    probs: List[float] = []
    for p in prices:
        val = _safe_float(p)
        if val is not None:
            probs.append(val)

    if not probs:
        return 0.0

    # Use the highest outcome price as the implied conflict probability
    return max(probs)


def _extract_volume(market: Dict[str, Any]) -> float:
    for key in ("volume", "volume24hr", "volume24h", "liquidity"):
        if key in market:
            val = _safe_float(market[key])
            if val is not None:
                return val
    return 0.0


def _prepare_polymarket(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relevant: List[Dict[str, Any]] = []
    for m in markets:
        question = m.get("question") or m.get("title") or m.get("name")
        if not isinstance(question, str):
            continue
        if not _market_matches_keywords(question):
            continue

        probability = _extract_probability(m)
        if probability == 0.0:
            continue
        volume = _extract_volume(m)

        relevant.append(
            {
                "question": question,
                "probability": probability,
                "volume": volume,
            }
        )

    # Sort by volume descending, then probability descending, and take top 5
    relevant.sort(key=lambda x: (x["volume"], x["probability"]), reverse=True)
    return relevant[:5]


def _compute_escalation_score(
    brent_change_pct: float | None,
    polymarket_markets: List[Dict[str, Any]],
) -> float:
    score = 50.0

    # Brent move rules
    if brent_change_pct is not None:
        if brent_change_pct >= 5.0:
            score += 15.0
        elif 2.0 <= brent_change_pct < 5.0:
            score += 8.0
        elif brent_change_pct < 0.0:
            score -= 10.0

    # Polymarket conflict odds rules
    max_prob = max((m.get("probability", 0.0) for m in polymarket_markets), default=0.0)

    if max_prob > 0.50:
        score += 20.0
    elif 0.30 <= max_prob <= 0.50:
        score += 10.0

    # Israel-related markets (Israel / Gaza / Netanyahu) > 40%
    for m in polymarket_markets:
        question = str(m.get("question", "")).lower()
        prob = float(m.get("probability", 0.0))
        if prob > 0.40 and any(k in question for k in ["israel", "gaza", "netanyahu"]):
            score += 8.0
            break

    # Clamp between 0 and 100
    score = max(0.0, min(100.0, score))
    return score


def _build_summary(
    brent: Dict[str, Any],
    wti: Dict[str, Any],
    polymarket_markets: List[Dict[str, Any]],
    escalation_score: float,
) -> str:
    brent_part = (
        f"Brent crude is {brent.get('change_pct', '0.0%')} at {brent.get('price', '?')} "
        f"as of {brent.get('as_of', 'unknown')}."
    )
    wti_part = (
        f"WTI crude is {wti.get('change_pct', '0.0%')} at {wti.get('price', '?')} "
        f"as of {wti.get('as_of', 'unknown')}."
    )

    if polymarket_markets:
        max_prob = max((m["probability"] for m in polymarket_markets), default=0.0)
        markets_part = (
            f" Polymarket conflict-related markets imply up to {max_prob * 100:.0f}% "
            f"probability on key scenarios."
        )
    else:
        markets_part = " No highly relevant Polymarket conflict markets were detected."

    score_part = f" Composite escalation score: {escalation_score:.1f}."
    return " ".join([brent_part, wti_part, markets_part, score_part])


async def _run_finint_agent_async(conflict: str) -> Dict[str, Any]:  # conflict kept for compatibility
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        raise RuntimeError("ALPHAVANTAGE_API_KEY is not set")

    async with httpx.AsyncClient(timeout=15.0) as client:
        brent_data, wti_data, polymarket_raw = await asyncio.gather(
            _fetch_alpha_series(client, "BRENT", api_key),
            _fetch_alpha_series(client, "WTI", api_key),
            _fetch_polymarket_markets(client),
        )

    # Parse Brent
    brent_as_of, brent_price, brent_change_pct = _parse_alpha_series(brent_data)
    brent_struct = {
        "price": f"{brent_price:.2f}" if brent_price is not None else None,
        "change_pct": _format_pct(brent_change_pct),
        "as_of": brent_as_of,
    }

    # Parse WTI
    wti_as_of, wti_price, wti_change_pct = _parse_alpha_series(wti_data)
    wti_struct = {
        "price": f"{wti_price:.2f}" if wti_price is not None else None,
        "change_pct": _format_pct(wti_change_pct),
        "as_of": wti_as_of,
    }

    # Polymarket
    polymarket_struct = _prepare_polymarket(polymarket_raw)

    # Escalation score
    escalation_score = _compute_escalation_score(brent_change_pct, polymarket_struct)

    # Summary
    summary = _build_summary(brent_struct, wti_struct, polymarket_struct, escalation_score)

    return {
        "brent": brent_struct,
        "wti": wti_struct,
        "polymarket": polymarket_struct,
        "escalation_score": escalation_score,
        "summary": summary,
    }


def run_finint_agent(conflict: str) -> Dict[str, Any]:
    """
    Public sync entrypoint for the FININT agent.

    Uses async httpx under the hood but exposes a synchronous API
    for compatibility with existing supervisor code.
    """
    return asyncio.run(_run_finint_agent_async(conflict))


