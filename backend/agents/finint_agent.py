"""
FININT Agent – Tool-Calling Agent
Fetches Brent/WTI oil prices, VIX, Fear & Greed Index (CNN-style), Polymarket conflict odds, OFAC sanctions, OFAC delta, and tracked wallet positions.
- Gamma API: https://gamma-api.polymarket.com (events, markets)
- Data API:  https://data-api.polymarket.com (positions, activity)
- OFAC SDN: Treasury bulk CSV (same source as DIPLO; FININT focus: sanctions/market relevance).
Optional: set POLYMARKET_BUILDER_API_KEY in .env (your personal builder API key) for authenticated requests.
"""
import asyncio
import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .config import DEFAULT_TIMEOUT
from .llm import run_agent_with_fallback
from .utils import run_async, safe_float, utc_now_iso, ScoreConfidence
from services.http_client import get_http_client

logger = logging.getLogger(__name__)

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"
# Fear & Greed: optional CNN source (e.g. FGI-Tracker https://github.com/leejustin/fgi-tracker); else Alternative.me
FEAR_GREED_CNN_API_URL = (os.getenv("FEAR_GREED_CNN_API_URL") or "").strip() or None
FEAR_GREED_FALLBACK_URL = "https://api.alternative.me/fng/?limit=1"

# Optional: POLYMARKET_BUILDER_API_KEY in .env for authenticated requests (e.g. higher rate limits).
def _polymarket_headers() -> Dict[str, str]:
    """Optional headers when POLYMARKET_BUILDER_API_KEY is set (your personal builder API key)."""
    key = os.getenv("POLYMARKET_BUILDER_API_KEY")
    if not key or not key.strip():
        return {}
    return {"Authorization": f"Bearer {key.strip()}"}

# Tracked wallets: (label, proxy wallet address). Use proxy address from profile URL.
TRACKED_WALLETS: List[tuple[str, str]] = [
    ("rundeep", "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"),
]

# Explicit Polymarket markets to always track (FININT) – fetched by slug via Gamma API.
# Focus: US–Iran, Israel–Iran, Trump military/foreign policy. 2025-spezifische Märkte entfernt (Stand 2026).
TRACKED_POLYMARKET_SLUGS = [
    "us-strikes-iran-by",
    "will-trump-announce-military-actions-against-iran-by-friday",
    "trump-announces-end-of-military-operations-against-iran-by",
    "trump-invokes-war-powers-against-iran-by",
    "will-trump-visit-china-by",
    "us-x-iran-ceasefire-by",
    "will-the-iranian-regime-fall-by-the-end-of-2026",
    "israel-strikes-iran-by-march-31-2026",  # Israel–Iran strike timing (adjust slug if Polymarket changes)
]

# Keywords for /events and /markets search: only geopolitics/conflict (avoids Oscars, Hungary PM, Warnock).
POLYMARKET_KEYWORDS = [
    "us forces", "enter iran", "strikes iran", "military operations", "military action",
    "trump", "iran", "ceasefire", "war powers", "congress authorizes",
    "visit china", "trade with", "cut off trade", "tariff", "sanctions",
    "middle east", "persian gulf", "strait of hormuz", "spain", "military base",
]

# Metaculus API – Prognosemärkte (zweiter Markt neben Polymarket)
METACULUS_API_BASE = "https://www.metaculus.com/api2/questions/"
METACULUS_CONFLICT_TERMS = ["iran", "us-iran", "war", "military", "strike", "nuclear", "israel", "gaza", "ukraine", "russia", "taiwan", "china"]

# Kalshi – optional second prediction market. Set KALSHI_API_BASE (e.g. https://trading-api.kalshi.com/trade-api/v2) to enable.
KALSHI_API_BASE = os.getenv("KALSHI_API_BASE", "").strip()
KALSHI_CONFLICT_TERMS = ["iran", "military", "strike", "nuclear", "israel", "gaza", "ukraine", "russia", "china", "taiwan"]

# Optional: Etherscan für On-Chain-Wallets (Whale/Sanktionen). Liste: (label, Ethereum-Adresse).
TRACKED_ETH_ADDRESSES: List[tuple[str, str]] = []

# Etherscan Free Tier: 3 calls/s, 100k calls/day – Delay zwischen Requests einhalten.
ETHERSCAN_RATE_LIMIT_DELAY_SEC = 0.35
MAX_ETHERSCAN_ADDRESSES_PER_RUN = 20

# Gold: optional METALS_API_KEY (metals-api.com) oder leer lassen
METALS_API_BASE = "https://metals-api.com/api"

# OFAC SDN (Treasury bulk CSV – free, no key). Keywords for conflict-relevant sanctions (market/sanctions context).
OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_CONFLICT_KEYWORDS: Dict[str, List[str]] = {
    "iran": ["iran", "irgc", "iranian", "tehran", "qods", "khamenei"],
    "us-iran": ["iran", "irgc", "iranian", "tehran"],
    "russia": ["russia", "russian", "ukraine", "donbas", "crimea", "putin"],
    "ukraine": ["ukraine", "russia", "donbas", "crimea"],
    "syria": ["syria", "syrian", "assad"],
    "north korea": ["dprk", "north korea", "kim jong"],
    "default": ["iran", "russia", "syria"],
}

# OFAC cache: raw CSV and TTL 6h (Treasury updates periodically)
_ofac_raw_csv: str | None = None
_ofac_cache_ts: float = 0.0
OFAC_CACHE_TTL = 6 * 3600  # 6h
# OFAC delta: keys from previous run (set of "name|type|program") to compute added_since_last_run
_ofac_previous_keys: set = set()

# Polymarket: only include markets with >48h left until end
POLYMARKET_MIN_HOURS_LEFT = 48


def _polymarket_end_ok(m: dict) -> bool:
    """True if market has no end date or ends more than POLYMARKET_MIN_HOURS_LEFT from now."""
    end_raw = m.get("endDate") or m.get("end_date") or m.get("closedTime") or m.get("end_date_iso")
    if not end_raw:
        return True
    try:
        if isinstance(end_raw, (int, float)):
            end_dt = datetime.fromtimestamp(end_raw, tz=timezone.utc)
        else:
            end_str = str(end_raw).replace("Z", "+00:00")[:19]
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        cutoff = (datetime.now(timezone.utc) + timedelta(hours=POLYMARKET_MIN_HOURS_LEFT)).isoformat()[:19]
        return end_dt.isoformat()[:19] >= cutoff
    except Exception:
        return True


# ─── Pydantic models ───────────────────────────────────────────────────────

class PricePoint(BaseModel):
    """Oil/gold/VIX price snapshot with change and fetched_at."""
    price: Optional[str] = None
    change_pct: str = "0.0%"
    as_of: str = ""
    fetched_at: str = Field(default_factory=utc_now_iso)


class FearGreedResult(BaseModel):
    """Fear & Greed Index (0–100; Alternative.me, CNN-style sentiment)."""
    value: Optional[int] = None
    value_classification: Optional[str] = None
    error: Optional[str] = None
    fetched_at: str = Field(default_factory=utc_now_iso)


class OfacDelta(BaseModel):
    """New OFAC entries since last run."""
    added_since_last_run: int = 0
    previous_total: int = 0
    current_total: int = 0


class FinintResult(BaseModel):
    """Structured FININT agent output."""
    brent: Dict[str, Any] = Field(default_factory=dict)
    wti: Dict[str, Any] = Field(default_factory=dict)
    gold: Dict[str, Any] = Field(default_factory=dict)
    vix: Dict[str, Any] = Field(default_factory=dict)
    fear_greed: Dict[str, Any] = Field(default_factory=dict)
    polymarket: List[Dict[str, Any]] = Field(default_factory=list)
    polymarket_fetched_at: Optional[str] = None
    metaculus: List[Dict[str, Any]] = Field(default_factory=list)
    metaculus_fetched_at: Optional[str] = None
    kalshi: List[Dict[str, Any]] = Field(default_factory=list)
    kalshi_fetched_at: Optional[str] = None
    ofac_sanctions: Dict[str, Any] = Field(default_factory=dict)
    ofac_delta: Optional[OfacDelta] = None
    tracked_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    tracked_wallets_fetched_at: Optional[str] = None
    tracked_chain_wallets: List[Dict[str, Any]] = Field(default_factory=list)
    tracked_chain_wallets_fetched_at: Optional[str] = None
    escalation_score: float = 0.0
    summary: str = ""
    score_confidence: ScoreConfidence = Field(default_factory=ScoreConfidence)
    fetched_at: str = Field(default_factory=utc_now_iso)


def _filter_ofac(csv_text: str, conflict: str) -> Dict[str, Any]:
    """Parse OFAC CSV and return conflict-relevant highlights (total_matches, sample, error, match_keys for delta)."""
    cl = (conflict or "").lower().strip()
    keywords = OFAC_CONFLICT_KEYWORDS.get("default", [])
    for k, v in OFAC_CONFLICT_KEYWORDS.items():
        if k != "default" and k in cl:
            keywords = v
            break
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        matches: List[Dict[str, Any]] = []
        match_keys: set = set()
        for row in reader:
            if not row:
                continue
            name = (row.get("name") or (row.get("firstName", "") + " " + row.get("lastName", "")).strip()).lower()
            program = (row.get("programs") or row.get("program", "") or "").lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                nm = (row.get("name") or (row.get("firstName", "") + " " + row.get("lastName", "")).strip() or "")
                ty = row.get("type") or ""
                prg = row.get("programs") or row.get("program") or ""
                matches.append({"name": nm, "type": ty, "program": prg})
                match_keys.add(f"{nm}|{ty}|{prg}")
        return {"total_matches": len(matches), "sample": matches[:15], "error": None, "match_keys": match_keys}
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e), "match_keys": set()}



def _extract_metaculus_prob(q: dict) -> float | None:
    """Extract probability from Metaculus question: community_prediction.full or .q2, or direct value."""
    prob = q.get("community_prediction")
    if isinstance(prob, dict):
        return safe_float(prob.get("full") or prob.get("q2"))
    return safe_float(prob)


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _clamp_prob(prob: float) -> float:
    """Normalize probability to 0–1 range (Gamma API returns 0–1, guard against 0–100)."""
    if prob > 1.0:
        prob = prob / 100.0
    return max(0.0, min(1.0, prob))


def _extract_end_date(m: dict) -> str | None:
    """Extract ISO end-date string from a Gamma API event/market dict."""
    raw = m.get("endDate") or m.get("end_date") or m.get("closedTime") or m.get("end_date_iso")
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        return str(raw)


def _normalize_polymarket_item(m: dict, slug: str = "") -> dict | None:
    """Build {question, probability, volume, url, end_date_iso} from Gamma API event or market object."""
    question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
    if not question:
        return None
    prices = m.get("outcomePrices") or []
    prob = 0.0
    if prices:
        prob = max((safe_float(p) or 0) for p in prices)
    for token in m.get("tokens") or []:
        p = safe_float(token.get("price"))
        if p and p > prob:
            prob = p
    prob = _clamp_prob(prob)
    volume = safe_float(m.get("volume") or m.get("volumeNum") or m.get("liquidity") or 0) or 0
    url_slug = slug or m.get("slug") or ""
    return {
        "question": question,
        "probability": round(prob, 3),
        "volume": round(volume, 0),
        "url": f"https://polymarket.com/event/{url_slug}" if url_slug else "",
        "end_date_iso": _extract_end_date(m),
    }


# ── Tools ──────────────────────────────────────────────────────────────────

def get_brent_price() -> Dict[str, Any]:
    """Fetch current Brent crude oil price and daily change from Alpha Vantage."""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ALPHAVANTAGE_URL, params={
                "function": "BRENT", "interval": "daily", "apikey": api_key
            })
            resp.raise_for_status()
            return resp.json()

    try:
        data = run_async(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = safe_float(latest.get("value"))
        prev_price = safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price and prev_price else None
        return {
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "as_of": latest.get("date", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def get_wti_price() -> Dict[str, Any]:
    """Fetch current WTI crude oil price and daily change from Alpha Vantage."""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ALPHAVANTAGE_URL, params={
                "function": "WTI", "interval": "daily", "apikey": api_key
            })
            resp.raise_for_status()
            return resp.json()

    try:
        data = run_async(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = safe_float(latest.get("value"))
        prev_price = safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price and prev_price else None
        return {
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "as_of": latest.get("date", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def get_polymarket_conflict_odds(conflict: str) -> List[Dict[str, Any]]:
    """Fetch Polymarket odds: tracked US–Iran/Trump/military/trade slugs first, then geopolitics keyword-matched events (excludes Oscars, Hungary PM, etc.)."""
    async def _fetch_tracked():
        """Fetch TRACKED_POLYMARKET_SLUGS via Gamma API GET /events/slug/{slug}. One row per event."""
        headers = _polymarket_headers()
        out = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for slug in TRACKED_POLYMARKET_SLUGS:
                try:
                    resp = await client.get(
                        f"{GAMMA_API_BASE}/events/slug/{slug}",
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        continue
                    event = resp.json()
                    if not isinstance(event, dict):
                        continue
                    question = (
                        event.get("title") or event.get("question") or event.get("name") or ""
                    ).strip()
                    if not question:
                        continue
                    # Max probability: top-level outcomePrices or across markets
                    prob = 0.0
                    for p in event.get("outcomePrices") or []:
                        v = safe_float(p)
                        if v and v > prob:
                            prob = v
                    for market in event.get("markets") or []:
                        if not isinstance(market, dict):
                            continue
                        for p in market.get("outcomePrices") or []:
                            v = safe_float(p)
                            if v and v > prob:
                                prob = v
                        for token in market.get("tokens") or []:
                            v = safe_float(token.get("price"))
                            if v and v > prob:
                                prob = v
                    prob = _clamp_prob(prob)
                    volume = safe_float(
                        event.get("volume") or event.get("volumeNum") or event.get("liquidity") or 0
                    ) or 0
                    out.append({
                        "question": question,
                        "probability": round(prob, 3),
                        "volume": round(volume, 0),
                        "url": f"https://polymarket.com/event/{slug}",
                        "end_date_iso": _extract_end_date(event),
                    })
                except Exception:
                    continue
        return out

    async def _fetch_all():
        headers = _polymarket_headers()
        results = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{GAMMA_API_BASE}/events",
                    params={"limit": 200, "active": "true", "closed": "false"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    events = resp.json()
                    if isinstance(events, list):
                        results.extend(events)
            except Exception:
                pass
            try:
                resp2 = await client.get(
                    f"{GAMMA_API_BASE}/markets",
                    params={"limit": 200, "active": "true", "closed": "false"},
                    headers=headers,
                )
                if resp2.status_code == 200:
                    markets = resp2.json()
                    if isinstance(markets, list):
                        results.extend(markets)
            except Exception:
                pass
        return results

    try:
        tracked = run_async(_fetch_tracked())
        tracked_questions = {str(t.get("question", ""))[:80] for t in tracked if t.get("question")}

        data = run_async(_fetch_all())
        relevant = []
        seen = set()

        for m in data:
            if not _polymarket_end_ok(m):
                continue
            question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
            if not question:
                continue
            key = question[:60]
            if key in seen:
                continue
            description = str(m.get("description") or "").lower()
            combined = f"{question.lower()} {description}"
            if not any(kw in combined for kw in POLYMARKET_KEYWORDS):
                continue
            if question[:80] in tracked_questions:
                continue
            seen.add(key)
            item = _normalize_polymarket_item(m)
            if item and (item.get("probability") or 0) > 0:  # 0.0 = resolved/inactive
                item["url"] = f"https://polymarket.com/event/{m.get('slug', '')}"
                relevant.append(item)

        relevant.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        # Tracked first (order as in TRACKED_POLYMARKET_SLUGS), then up to 10 keyword matches
        return tracked + relevant[:10]
    except Exception as e:
        return [{"error": str(e)}]


def get_metaculus_conflict_questions(conflict: str) -> List[Dict[str, Any]]:
    """Fetch open Metaculus prediction questions relevant to conflict (search + filter)."""
    async def _fetch():
        out = []
        search_term = (conflict or "").strip() or "geopolitics"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    METACULUS_API_BASE,
                    params={
                        "search": search_term,
                        "status": "open",
                        "limit": 20,
                        "order_by": "-activity",
                    },
                )
                if resp.status_code != 200:
                    return [{"error": f"Metaculus API {resp.status_code}"}]
                data = resp.json()
        except Exception as e:
            return [{"error": str(e)}]
        results = data.get("results") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(results, list):
            return []
        cl = (conflict or "").lower()
        keywords = [t for t in METACULUS_CONFLICT_TERMS if t in cl] or ["war", "military", "iran", "ukraine"]
        for q in results[:15]:
            if not isinstance(q, dict):
                continue
            title = (q.get("title") or "").strip()
            if not title:
                continue
            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue
            prob = _extract_metaculus_prob(q)
            out.append({
                "title": title[:200],
                "probability": round(prob, 3) if prob is not None else None,
                "url": f"https://www.metaculus.com/questions/{q.get('id', '')}",
                "resolve_time": q.get("resolve_time"),
            })
        return out[:10]

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


def get_gold_price() -> Dict[str, Any]:
    """Fetch current gold (XAU) price in USD. Uses metals-api.com if METALS_API_KEY is set."""
    api_key = (os.getenv("METALS_API_KEY") or os.getenv("METALPRICEAPI_KEY") or "").strip()
    if not api_key:
        return {"error": "METALS_API_KEY not set (optional; get key at metals-api.com)"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{METALS_API_BASE}/latest",
                params={"access_key": api_key, "base": "XAU", "currencies": "USD"},
            )
            if resp.status_code != 200:
                return {"error": f"Metals API {resp.status_code}"}
            return resp.json()

    try:
        data = run_async(_fetch())
        if isinstance(data, dict) and "error" in data:
            return data
        rates = (data.get("rates") or {}) if isinstance(data, dict) else {}
        usd = safe_float(rates.get("USD"))
        if usd is None:
            return {"error": "No USD rate in response"}
        return {
            "price": f"{usd:.2f}",
            "change_pct": "0.0%",
            "as_of": (data.get("date") or ""),
        }
    except Exception as e:
        return {"error": str(e)}


def get_tracked_chain_wallets() -> List[Dict[str, Any]]:
    """
    Fetch Ethereum balances for tracked addresses via Etherscan (Free Tier).
    Respects 3 calls/s (delay between requests) and 100k calls/day. Attribution required – see docs/API-KEYS.md.
    """
    api_key = (os.getenv("ETHEREUM_ETHERSCAN_API_KEY") or os.getenv("ETHERSCAN_API_KEY") or "").strip()
    addresses = (TRACKED_ETH_ADDRESSES or [])[:MAX_ETHERSCAN_ADDRESSES_PER_RUN]
    if not addresses:
        return []
    if not api_key:
        return [{"error": "ETHEREUM_ETHERSCAN_API_KEY not set"}]

    async def _fetch():
        out: List[Dict[str, Any]] = []
        delay = ETHERSCAN_RATE_LIMIT_DELAY_SEC
        async with httpx.AsyncClient(timeout=15.0) as client:
            for i, (label, address) in enumerate(addresses):
                if i > 0:
                    await asyncio.sleep(delay)
                try:
                    resp = await client.get(
                        "https://api.etherscan.io/api",
                        params={
                            "module": "account",
                            "action": "balance",
                            "address": address,
                            "tag": "latest",
                            "apikey": api_key,
                        },
                    )
                    if resp.status_code != 200:
                        out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                        continue
                    data = resp.json()
                    if data.get("status") != "1" and data.get("message") != "OK":
                        out.append({"wallet": label, "address": address[:10] + "...", "error": data.get("message", "API error")})
                        continue
                    wei = int(data.get("result", 0))
                    eth = wei / 1e18
                    out.append({
                        "wallet": label,
                        "address": address[:10] + "...",
                        "balance_eth": round(eth, 4),
                        "balance_wei": str(wei),
                    })
                except Exception as e:
                    out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
        if out:
            out.append({"_attribution": "Etherscan (etherscan.io)"})
        return out

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── Async fetches (for parallel run) ────────────────────────────────────────


async def _fetch_oil_price(client: Any, function: str) -> Dict[str, Any]:
    """Fetch Brent or WTI from Alpha Vantage (function='BRENT' or 'WTI')."""
    fetched_at = utc_now_iso()
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set", "fetched_at": fetched_at}
    try:
        resp = await client.request("GET", ALPHAVANTAGE_URL, params={"function": function, "interval": "daily", "apikey": api_key}, timeout=DEFAULT_TIMEOUT)
        data = resp.json()
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data", "fetched_at": fetched_at}
        latest, prev = series[0], series[1]
        price, prev_price = safe_float(latest.get("value")), safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price and prev_price else None
        return {"price": f"{price:.2f}" if price else None, "change_pct": _format_pct(change_pct), "as_of": latest.get("date", ""), "fetched_at": fetched_at}
    except Exception as e:
        logger.debug("FININT: %s fetch failed: %s", function, e)
        return {"error": str(e), "fetched_at": fetched_at}


async def _fetch_brent(client: Any) -> Dict[str, Any]:
    return await _fetch_oil_price(client, "BRENT")


async def _fetch_wti(client: Any) -> Dict[str, Any]:
    return await _fetch_oil_price(client, "WTI")


async def _fetch_gold(client: Any) -> Dict[str, Any]:
    fetched_at = utc_now_iso()
    api_key = (os.getenv("METALS_API_KEY") or os.getenv("METALPRICEAPI_KEY") or "").strip()
    if not api_key:
        return {"error": "METALS_API_KEY not set (optional; get key at metals-api.com)", "fetched_at": fetched_at}
    try:
        resp = await client.request("GET", f"{METALS_API_BASE}/latest", params={"access_key": api_key, "base": "XAU", "currencies": "USD"}, timeout=12.0)
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            return {**data, "fetched_at": fetched_at}
        rates = (data.get("rates") or {}) if isinstance(data, dict) else {}
        usd = safe_float(rates.get("USD"))
        if usd is None:
            return {"error": "No USD rate in response", "fetched_at": fetched_at}
        return {"price": f"{usd:.2f}", "change_pct": "0.0%", "as_of": (data.get("date") or ""), "fetched_at": fetched_at}
    except Exception as e:
        return {"error": str(e), "fetched_at": fetched_at}


async def _fetch_fear_greed(client: Any) -> Dict[str, Any]:
    """Fetch Fear & Greed Index: optional CNN source (FEAR_GREED_CNN_API_URL / FGI-Tracker), else Alternative.me. Returns value 0–100, classification, fetched_at."""
    fetched_at = utc_now_iso()

    def _parse_item(item: dict) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        value = item.get("value")
        v = int(value) if value is not None else None
        if v is not None and (v < 0 or v > 100):
            v = None
        classification = item.get("value_classification") or item.get("classification") or item.get("label")
        return {"value": v, "value_classification": classification, "fetched_at": fetched_at}

    if FEAR_GREED_CNN_API_URL:
        try:
            resp = await client.request("GET", FEAR_GREED_CNN_API_URL, timeout=10.0)
            data = resp.json()
            if isinstance(data, dict):
                arr = data.get("data") or data.get("values") or data.get("results")
                if isinstance(arr, list) and arr:
                    out = _parse_item(arr[0] if isinstance(arr[0], dict) else {})
                    if out.get("value") is not None:
                        return out
                if data.get("value") is not None:
                    out = _parse_item(data)
                    if out.get("value") is not None:
                        return out
            if isinstance(data, list) and data and isinstance(data[0], dict):
                out = _parse_item(data[0])
                if out.get("value") is not None:
                    return out
        except Exception:
            pass

    try:
        resp = await client.request("GET", FEAR_GREED_FALLBACK_URL, timeout=10.0)
        data = resp.json()
        arr = data.get("data") if isinstance(data, dict) else []
        if not arr or not isinstance(arr, list):
            return {"error": "No data", "fetched_at": fetched_at}
        item = arr[0]
        out = _parse_item(item)
        if out.get("value") is not None:
            return out
        return {"error": "Invalid item", "fetched_at": fetched_at}
    except Exception as e:
        return {"error": str(e), "fetched_at": fetched_at}


async def _fetch_vix(client: Any) -> Dict[str, Any]:
    """Fetch VIX (CBOE Volatility Index) via Alpha Vantage function=VIX or TIME_SERIES_DAILY symbol=VIX."""
    fetched_at = utc_now_iso()
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set", "fetched_at": fetched_at}
    try:
        resp = await client.request(
            "GET",
            ALPHAVANTAGE_URL,
            params={"function": "VIX", "interval": "daily", "apikey": api_key},
            timeout=15.0,
        )
        data = resp.json()
        if isinstance(data, dict) and data.get("Note"):
            return {"error": "Alpha Vantage rate limit", "fetched_at": fetched_at}
        series = data.get("data", [])
        if not series or len(series) < 2:
            return {"error": "Insufficient VIX data", "fetched_at": fetched_at}
        latest, prev = series[0], series[1]
        price = safe_float(latest.get("value"))
        prev_price = safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price is not None and prev_price else None
        return {
            "price": f"{price:.2f}" if price is not None else None,
            "change_pct": _format_pct(change_pct),
            "as_of": latest.get("date", ""),
            "fetched_at": fetched_at,
        }
    except Exception as e:
        return {"error": str(e), "fetched_at": fetched_at}


async def _fetch_polymarket(client: Any, conflict: str) -> Dict[str, Any]:
    """Fetch Polymarket odds; returns {items: [...], fetched_at: ...}. Only items with probability > 0 and endDate > 48h."""
    fetched_at = utc_now_iso()
    headers = _polymarket_headers()

    tracked: List[Dict[str, Any]] = []
    try:
        for slug in TRACKED_POLYMARKET_SLUGS:
            resp = await client.request("GET", f"{GAMMA_API_BASE}/events/slug/{slug}", headers=headers or {}, timeout=15.0)
            if resp.status_code != 200:
                continue
            event = resp.json()
            if not isinstance(event, dict):
                continue
            if not _polymarket_end_ok(event):
                continue
            question = (event.get("title") or event.get("question") or event.get("name") or "").strip()
            if not question:
                continue
            prob = 0.0
            for p in event.get("outcomePrices") or []:
                v = safe_float(p)
                if v and v > prob:
                    prob = v
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                for p in market.get("outcomePrices") or []:
                    v = safe_float(p)
                    if v and v > prob:
                        prob = v
                for token in market.get("tokens") or []:
                    v = safe_float(token.get("price"))
                    if v and v > prob:
                        prob = v
            prob = _clamp_prob(prob)
            volume = safe_float(event.get("volume") or event.get("volumeNum") or event.get("liquidity") or 0) or 0
            item = {"question": question, "probability": round(prob, 3), "volume": round(volume, 0), "url": f"https://polymarket.com/event/{slug}", "end_date_iso": _extract_end_date(event)}
            if item.get("probability", 0) > 0:
                tracked.append(item)
    except Exception:
        pass
    tracked_questions = {str(t.get("question", ""))[:80] for t in tracked if t.get("question")}
    results: List[Dict] = []
    try:
        for url_suffix, params in [
            (f"{GAMMA_API_BASE}/events", {"limit": 200, "active": "true", "closed": "false"}),
            (f"{GAMMA_API_BASE}/markets", {"limit": 200, "active": "true", "closed": "false"}),
        ]:
            resp = await client.request("GET", url_suffix, params=params, headers=headers or {}, timeout=20.0)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for m in (data if isinstance(data, list) else []):
                if not _polymarket_end_ok(m):
                    continue
                question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
                if not question or question[:80] in tracked_questions:
                    continue
                key = question[:60]
                if key in {r.get("question", "")[:60] for r in results}:
                    continue
                combined = f"{(m.get('description') or '').lower()} {question.lower()}"
                if not any(kw in combined for kw in POLYMARKET_KEYWORDS):
                    continue
                item = _normalize_polymarket_item(m)
                if item and (item.get("probability") or 0) > 0:
                    item["url"] = f"https://polymarket.com/event/{m.get('slug', '')}"
                    results.append(item)
    except Exception:
        pass
    results.sort(key=lambda x: x.get("volume") or 0, reverse=True)
    return {"items": tracked + results[:10], "fetched_at": fetched_at}


async def _fetch_metaculus(client: Any, conflict: str) -> Dict[str, Any]:
    """Fetch Metaculus questions; returns {items: [...], fetched_at: ...}. Uses _extract_metaculus_prob."""
    fetched_at = utc_now_iso()
    search_term = (conflict or "").strip() or "geopolitics"
    try:
        resp = await client.request("GET", METACULUS_API_BASE, params={"search": search_term, "status": "open", "limit": 20, "order_by": "-activity"}, timeout=15.0)
        if resp.status_code != 200:
            return {"items": [{"error": f"Metaculus API {resp.status_code}"}], "fetched_at": fetched_at}
        data = resp.json()
    except Exception as e:
        return {"items": [{"error": str(e)}], "fetched_at": fetched_at}
    results = data.get("results") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not isinstance(results, list):
        return {"items": [], "fetched_at": fetched_at}
    cl = (conflict or "").lower()
    keywords = [t for t in METACULUS_CONFLICT_TERMS if t in cl] or ["war", "military", "iran", "ukraine"]
    out = []
    for q in results[:15]:
        if not isinstance(q, dict):
            continue
        title = (q.get("title") or "").strip()
        if not title or not any(kw in title.lower() for kw in keywords):
            continue
        prob = _extract_metaculus_prob(q)
        out.append({
            "title": title[:200],
            "probability": round(prob, 3) if prob is not None else None,
            "url": f"https://www.metaculus.com/questions/{q.get('id', '')}",
            "resolve_time": q.get("resolve_time"),
        })
    return {"items": out[:10], "fetched_at": fetched_at}


async def _fetch_kalshi(client: Any, conflict: str) -> Dict[str, Any]:
    """Fetch Kalshi prediction markets (optional). Set KALSHI_API_BASE to enable. Returns {items: [...], fetched_at: ...}."""
    fetched_at = utc_now_iso()
    if not KALSHI_API_BASE:
        return {"items": [], "fetched_at": fetched_at}
    try:
        resp = await client.request(
            "GET",
            f"{KALSHI_API_BASE.rstrip('/')}/events",
            params={"limit": 50, "status": "open"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return {"items": [{"error": f"Kalshi API {resp.status_code}"}], "fetched_at": fetched_at}
        data = resp.json()
    except Exception as e:
        return {"items": [{"error": str(e)}], "fetched_at": fetched_at}
    events = data.get("events") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not isinstance(events, list):
        return {"items": [], "fetched_at": fetched_at}
    cl = (conflict or "").lower()
    keywords = [t for t in KALSHI_CONFLICT_TERMS if t in cl] or ["iran", "military", "war"]
    out: List[Dict[str, Any]] = []
    for ev in events[:15]:
        if not isinstance(ev, dict):
            continue
        title = (ev.get("title") or ev.get("event_ticker") or "").strip()
        if not title or not any(kw in title.lower() for kw in keywords):
            continue
        # Kalshi yes_bid/yes_ask or last_price as probability proxy
        yes_bid = safe_float(ev.get("yes_bid"))
        yes_ask = safe_float(ev.get("yes_ask"))
        prob = (yes_bid + yes_ask) / 2 if (yes_bid is not None and yes_ask is not None) else safe_float(ev.get("last_price"))
        if prob is None:
            prob = 0.0
        out.append({
            "question": title[:200],
            "probability": round(prob, 3),
            "url": f"https://kalshi.com/markets/{ev.get('event_ticker', ev.get('ticker', ''))}",
            "volume": safe_float(ev.get("volume")) or 0,
        })
    return {"items": out[:10], "fetched_at": fetched_at}


async def _fetch_ofac_cached(client: Any, conflict: str) -> Dict[str, Any]:
    """Fetch OFAC SDN (or use 6h cache), filter by conflict; returns total_matches, sample, error, fetched_at, ofac_delta."""
    global _ofac_raw_csv, _ofac_cache_ts, _ofac_previous_keys
    fetched_at = datetime.now(timezone.utc).isoformat()
    if _ofac_raw_csv is not None and (time.monotonic() - _ofac_cache_ts) < OFAC_CACHE_TTL:
        out = _filter_ofac(_ofac_raw_csv, conflict)
        out["fetched_at"] = fetched_at
    else:
        try:
            resp = await client.request("GET", OFAC_SDN_CSV_URL, timeout=30.0)
            _ofac_raw_csv = resp.text
            _ofac_cache_ts = time.monotonic()
            out = _filter_ofac(_ofac_raw_csv, conflict)
            out["fetched_at"] = fetched_at
        except Exception as e:
            out = {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": fetched_at, "match_keys": set()}

    current_keys = out.get("match_keys") or set()
    previous_total = len(_ofac_previous_keys)
    current_total = len(current_keys)
    added = len(current_keys - _ofac_previous_keys)
    out["ofac_delta"] = {
        "added_since_last_run": added,
        "previous_total": previous_total,
        "current_total": current_total,
    }
    if out.get("error") is None:
        _ofac_previous_keys = current_keys
    return out


async def _fetch_wallet_positions(client: Any) -> Dict[str, Any]:
    """Fetch Polymarket positions for tracked wallets; returns {items: [...], fetched_at: ...}."""
    fetched_at = utc_now_iso()
    if not TRACKED_WALLETS:
        return {"items": [], "fetched_at": fetched_at}
    out = []
    headers = _polymarket_headers()
    for label, address in TRACKED_WALLETS:
        try:
            resp = await client.request("GET", f"{DATA_API_BASE}/positions", params={"user": address, "limit": 50, "sortBy": "TOKENS", "sortDirection": "DESC"}, headers=headers or {}, timeout=15.0)
            if resp.status_code != 200:
                out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                continue
            data = resp.json()
            positions = data if isinstance(data, list) else data.get("data", data.get("positions", []))
            if not isinstance(positions, list):
                positions = []
            items = []
            for p in positions[:20]:
                title = p.get("title") or p.get("market") or p.get("question") or ""
                size = safe_float(p.get("size") or p.get("tokens") or 0)
                avg_price = safe_float(p.get("avgPrice") or p.get("price"))
                items.append({"title": title[:120] if title else "", "size": round(size, 2) if size else 0, "avgPrice": round(avg_price, 4) if avg_price else None})
            out.append({"wallet": label, "address": address[:10] + "...", "position_count": len(positions), "positions": items})
        except Exception as e:
            out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
    return {"items": out, "fetched_at": fetched_at}


async def _fetch_chain_wallets(client: Any) -> Dict[str, Any]:
    """Fetch Etherscan balances for tracked addresses; returns {items: [...], fetched_at: ...}."""
    fetched_at = utc_now_iso()
    api_key = (os.getenv("ETHEREUM_ETHERSCAN_API_KEY") or os.getenv("ETHERSCAN_API_KEY") or "").strip()
    addresses = (TRACKED_ETH_ADDRESSES or [])[:MAX_ETHERSCAN_ADDRESSES_PER_RUN]
    if not addresses:
        return {"items": [], "fetched_at": fetched_at}
    if not api_key:
        return {"items": [{"error": "ETHEREUM_ETHERSCAN_API_KEY not set"}], "fetched_at": fetched_at}
    out: List[Dict[str, Any]] = []
    for i, (label, address) in enumerate(addresses):
        if i > 0:
            await asyncio.sleep(ETHERSCAN_RATE_LIMIT_DELAY_SEC)
        try:
            resp = await client.request("GET", "https://api.etherscan.io/api", params={"module": "account", "action": "balance", "address": address, "tag": "latest", "apikey": api_key}, timeout=15.0)
            if resp.status_code != 200:
                out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                continue
            data = resp.json()
            if data.get("status") != "1" and data.get("message") != "OK":
                out.append({"wallet": label, "address": address[:10] + "...", "error": data.get("message", "API error")})
                continue
            wei = int(data.get("result", 0))
            out.append({"wallet": label, "address": address[:10] + "...", "balance_eth": round(wei / 1e18, 4), "balance_wei": str(wei)})
        except Exception as e:
            out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
    if out:
        out.append({"_attribution": "Etherscan (etherscan.io)"})
    return {"items": out, "fetched_at": fetched_at}


async def _run_all_parallel(conflict: str) -> Dict[str, Any]:
    """Run all FININT fetches in parallel with shared client; return_exceptions=True; return FinintResult as dict."""
    client = get_http_client()
    brent, wti, gold, vix, fear_greed, polymarket, metaculus, kalshi, ofac, wallets, chain = await asyncio.gather(
        _fetch_brent(client),
        _fetch_wti(client),
        _fetch_gold(client),
        _fetch_vix(client),
        _fetch_fear_greed(client),
        _fetch_polymarket(client, conflict),
        _fetch_metaculus(client, conflict),
        _fetch_kalshi(client, conflict),
        _fetch_ofac_cached(client, conflict),
        _fetch_wallet_positions(client),
        _fetch_chain_wallets(client),
        return_exceptions=True,
    )

    def _unwrap(x: Any, default: Any) -> Any:
        if isinstance(x, Exception):
            return {"error": str(x), "fetched_at": utc_now_iso()}
        return x

    brent = _unwrap(brent, {})
    wti = _unwrap(wti, {})
    gold = _unwrap(gold, {})
    vix = _unwrap(vix, {})
    fear_greed = _unwrap(fear_greed, {})
    polymarket = _unwrap(polymarket, {"items": [], "fetched_at": utc_now_iso()})
    metaculus = _unwrap(metaculus, {"items": [], "fetched_at": utc_now_iso()})
    kalshi = _unwrap(kalshi, {"items": [], "fetched_at": utc_now_iso()})
    ofac = _unwrap(ofac, {"total_matches": 0, "sample": [], "error": None, "fetched_at": utc_now_iso(), "ofac_delta": {"added_since_last_run": 0, "previous_total": 0, "current_total": 0}})
    wallets = _unwrap(wallets, {"items": [], "fetched_at": utc_now_iso()})
    chain = _unwrap(chain, {"items": [], "fetched_at": utc_now_iso()})

    polymarket_list = polymarket.get("items", []) if isinstance(polymarket, dict) else []
    metaculus_list = metaculus.get("items", []) if isinstance(metaculus, dict) else []
    kalshi_list = kalshi.get("items", []) if isinstance(kalshi, dict) else []
    tracked_wallets_list = wallets.get("items", []) if isinstance(wallets, dict) else []
    tracked_chain_list = chain.get("items", []) if isinstance(chain, dict) else []
    if not isinstance(polymarket_list, list):
        polymarket_list = []
    if not isinstance(metaculus_list, list):
        metaculus_list = []
    if not isinstance(kalshi_list, list):
        kalshi_list = []
    if not isinstance(tracked_wallets_list, list):
        tracked_wallets_list = []
    if not isinstance(tracked_chain_list, list):
        tracked_chain_list = []

    base = 50.0
    if isinstance(brent, dict) and "error" not in brent and brent.get("change_pct"):
        cp = brent.get("change_pct") or "0%"
        if "+" in cp and "%" in cp:
            try:
                v = float(cp.replace("%", "").strip())
                if v > 5:
                    base += 15
                elif v > 2:
                    base += 8
            except ValueError:
                pass
        if "-" in cp:
            base -= 10
    if polymarket_list:
        max_prob = max((safe_float(p.get("probability")) or 0) for p in polymarket_list if isinstance(p, dict) and "error" not in p)
        if max_prob and max_prob > 0.5:
            base += 20
        elif max_prob and max_prob > 0.3:
            base += 10
    if metaculus_list:
        meta_probs = [safe_float(p.get("probability")) for p in metaculus_list if isinstance(p, dict) and "error" not in p and p.get("probability") is not None]
        if meta_probs:
            max_meta = max(meta_probs)
            if max_meta and max_meta > 0.5:
                base += 8
            elif max_meta and max_meta > 0.3:
                base += 4
    if kalshi_list:
        kalshi_probs = [safe_float(p.get("probability")) for p in kalshi_list if isinstance(p, dict) and "error" not in p and p.get("probability") is not None]
        if kalshi_probs and max(kalshi_probs) > 0.5:
            base += 5
    ofac_total = int(ofac.get("total_matches") or 0) if isinstance(ofac, dict) and "error" not in ofac else 0
    if ofac_total > 200:
        base += 6
    elif ofac_total > 50:
        base += 3
    vix_price = safe_float(vix.get("price")) if isinstance(vix, dict) and "error" not in vix else None
    if vix_price is not None and vix_price > 25:
        base += 2
    fg_val = fear_greed.get("value") if isinstance(fear_greed, dict) and "error" not in fear_greed else None
    if fg_val is not None and fg_val <= 25:
        base += 2
    score = max(0.0, min(100.0, base))

    source_keys = ["brent", "wti", "gold", "vix", "fear_greed", "polymarket", "metaculus", "kalshi", "ofac_sanctions", "tracked_wallets", "tracked_chain_wallets"]
    results_by_key = {
        "brent": brent, "wti": wti, "gold": gold, "vix": vix, "fear_greed": fear_greed,
        "polymarket": polymarket_list, "metaculus": metaculus_list, "kalshi": kalshi_list,
        "ofac_sanctions": ofac, "tracked_wallets": tracked_wallets_list, "tracked_chain_wallets": tracked_chain_list,
    }
    sources_ok = []
    sources_missing = []
    for k in source_keys:
        val = results_by_key.get(k)
        if k == "ofac_sanctions":
            ok = isinstance(val, dict) and "error" not in val and val.get("error") is None
        elif k in ("polymarket", "metaculus", "kalshi", "tracked_wallets", "tracked_chain_wallets"):
            ok = isinstance(val, list) and len(val) > 0 and not (len(val) == 1 and isinstance(val[0], dict) and val[0].get("error"))
        else:
            ok = isinstance(val, dict) and "error" not in val
        if ok:
            sources_ok.append(k)
        else:
            sources_missing.append(k)
    api_keys_available = len(sources_ok)
    score_confidence = ScoreConfidence(
        level="high" if api_keys_available >= 2 else "low",
        sources_ok=sources_ok,
        sources_missing=sources_missing,
    )

    ofac_delta_data = ofac.get("ofac_delta") if isinstance(ofac, dict) else None
    ofac_delta = None
    if ofac_delta_data and isinstance(ofac_delta_data, dict):
        ofac_delta = OfacDelta(
            added_since_last_run=int(ofac_delta_data.get("added_since_last_run") or 0),
            previous_total=int(ofac_delta_data.get("previous_total") or 0),
            current_total=int(ofac_delta_data.get("current_total") or 0),
        )

    def _ofac_for_output(o: Dict[str, Any]) -> Dict[str, Any]:
        """Drop match_keys (set) so JSON serialization succeeds."""
        return {k: v for k, v in (o or {}).items() if k != "match_keys"}

    def _price_fallback(p: Any, key: str) -> Dict[str, Any]:
        if isinstance(p, dict) and "error" not in p:
            return p
        return {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": p.get("fetched_at", utc_now_iso()) if isinstance(p, dict) else utc_now_iso()}

    result = FinintResult(
        brent=_price_fallback(brent, "brent"),
        wti=_price_fallback(wti, "wti"),
        gold=_price_fallback(gold, "gold"),
        vix=_price_fallback(vix, "vix"),
        fear_greed=fear_greed if isinstance(fear_greed, dict) and "error" not in fear_greed else {"error": fear_greed.get("error") if isinstance(fear_greed, dict) else "unknown", "fetched_at": utc_now_iso()},
        polymarket=[p for p in polymarket_list if isinstance(p, dict) and "error" not in p],
        polymarket_fetched_at=polymarket.get("fetched_at") if isinstance(polymarket, dict) else None,
        metaculus=[m for m in metaculus_list if isinstance(m, dict) and "error" not in m],
        metaculus_fetched_at=metaculus.get("fetched_at") if isinstance(metaculus, dict) else None,
        kalshi=[k for k in kalshi_list if isinstance(k, dict) and "error" not in k],
        kalshi_fetched_at=kalshi.get("fetched_at") if isinstance(kalshi, dict) else None,
        ofac_sanctions=_ofac_for_output(ofac) if isinstance(ofac, dict) and ofac.get("error") is None else {"total_matches": 0, "sample": [], "error": ofac.get("error") if isinstance(ofac, dict) else None, "fetched_at": ofac.get("fetched_at", utc_now_iso()) if isinstance(ofac, dict) else utc_now_iso(), "ofac_delta": None},
        ofac_delta=ofac_delta,
        tracked_wallets=[w for w in tracked_wallets_list if isinstance(w, dict)],
        tracked_wallets_fetched_at=wallets.get("fetched_at") if isinstance(wallets, dict) else None,
        tracked_chain_wallets=[w for w in tracked_chain_list if isinstance(w, dict) and "balance_eth" in w],
        tracked_chain_wallets_fetched_at=chain.get("fetched_at") if isinstance(chain, dict) else None,
        escalation_score=round(score, 1),
        summary="FININT (rule-based): oil, gold, VIX, Fear & Greed, Polymarket, Metaculus, OFAC sanctions and delta, wallet data.",
        score_confidence=score_confidence,
        fetched_at=utc_now_iso(),
    )
    return result.model_dump(mode="json")


def get_ofac_sanctions_highlights(conflict: str) -> Dict[str, Any]:
    """
    Fetch OFAC SDN list and return conflict-relevant sanctions highlights (for markets/finance context).
    Same Treasury CSV as DIPLO; FININT uses this for sanctions exposure and market risk.
    """
    try:
        return run_async(_fetch_ofac_cached(get_http_client(), conflict))
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}


def get_tracked_wallet_positions() -> List[Dict[str, Any]]:
    """Fetch current Polymarket positions for tracked wallets (e.g. rundeep) via Data API."""
    if not TRACKED_WALLETS:
        return []
    async def _fetch():
        out = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for label, address in TRACKED_WALLETS:
                try:
                    resp = await client.get(
                        f"{DATA_API_BASE}/positions",
                        params={"user": address, "limit": 50, "sortBy": "TOKENS", "sortDirection": "DESC"},
                        headers=_polymarket_headers(),
                    )
                    if resp.status_code != 200:
                        out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                        continue
                    data = resp.json()
                    positions = data if isinstance(data, list) else data.get("data", data.get("positions", []))
                    if not isinstance(positions, list):
                        positions = []
                    # Keep fields useful for conflict relevance
                    items = []
                    for p in positions[:20]:
                        title = p.get("title") or p.get("market") or p.get("question") or ""
                        size = safe_float(p.get("size") or p.get("tokens") or 0)
                        avg_price = safe_float(p.get("avgPrice") or p.get("price"))
                        items.append({
                            "title": title[:120] if title else "",
                            "size": round(size, 2) if size else 0,
                            "avgPrice": round(avg_price, 4) if avg_price else None,
                        })
                    out.append({
                        "wallet": label,
                        "address": address[:10] + "...",
                        "position_count": len(positions),
                        "positions": items,
                    })
                except Exception as e:
                    out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
        return out
    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── Rule-based tool chain (uses async parallel run) ──────────────────────────

def _run_rule_based_finint(conflict: str) -> Dict[str, Any]:
    """Execute FININT via async parallel fetches; returns result with fetched_at and score_confidence."""
    try:
        return run_async(_run_all_parallel(conflict))
    except Exception as e:
        utc = datetime.now(timezone.utc).isoformat()
        return {
            "brent": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "wti": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "gold": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "vix": {"price": None, "change_pct": "0.0%", "as_of": "", "fetched_at": utc},
            "fear_greed": {"error": str(e), "fetched_at": utc},
            "polymarket": [],
            "metaculus": [],
            "ofac_sanctions": {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": utc},
            "ofac_delta": None,
            "tracked_wallets": [],
            "tracked_chain_wallets": [],
            "escalation_score": 50.0,
            "summary": f"FININT error: {e}",
            "score_confidence": {"level": "low", "sources_ok": [], "sources_missing": ["brent", "wti", "gold", "vix", "fear_greed", "polymarket", "metaculus", "kalshi", "ofac_sanctions", "tracked_wallets", "tracked_chain_wallets"]},
            "fetched_at": utc,
        }


# ── Agent ──────────────────────────────────────────────────────────────────

FININT_SYSTEM = """You are a FININT (Financial Intelligence) analyst.
Your job: fetch oil prices, gold, Polymarket and Metaculus conflict odds, and tracked wallet positions (Polymarket + Ethereum), then compute an escalation score (0-100).

Scoring rules:
- Base: 50
- Brent > +5%: +15, Brent +2-5%: +8, Brent negative: -10
- Polymarket conflict odds > 50%: +20, 30-50%: +10
- Metaculus high conflict probability: +8 (>.5) or +4 (>.3)
- Tracked wallets (Polymarket + chain) with large conflict-related positions: consider in summary
- Clamp to [0, 100]

Always call all tools, then return ONLY valid JSON:
{
  "brent": {"price": "...", "change_pct": "...", "as_of": "..."},
  "wti": {"price": "...", "change_pct": "...", "as_of": "..."},
  "gold": {"price": "...", "change_pct": "...", "as_of": "..."},
  "polymarket": [...],
  "metaculus": [...],
  "ofac_sanctions": {"total_matches": N, "sample": [{"name", "type", "program"}]},
  "tracked_wallets": [{"wallet": "...", "position_count": N, "positions": [...]}],
  "tracked_chain_wallets": [{"wallet": "...", "balance_eth": N}],
  "escalation_score": <number>,
  "summary": "<1-2 sentence summary; mention sanctions/market exposure if relevant>"
}
No markdown, no explanation, just JSON."""


_FININT_TOOL_FNS = {
    "get_brent_price": get_brent_price,
    "get_wti_price": get_wti_price,
    "get_gold_price": get_gold_price,
    "get_polymarket_conflict_odds": get_polymarket_conflict_odds,
    "get_metaculus_conflict_questions": get_metaculus_conflict_questions,
    "get_ofac_sanctions_highlights": get_ofac_sanctions_highlights,
    "get_tracked_wallet_positions": get_tracked_wallet_positions,
    "get_tracked_chain_wallets": get_tracked_chain_wallets,
}
_FININT_TOOL_SCHEMAS = [
    {"name": "get_brent_price", "description": "Fetch current Brent crude oil price from Alpha Vantage.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_wti_price", "description": "Fetch current WTI crude oil price from Alpha Vantage.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_gold_price", "description": "Fetch current gold (XAU) price in USD (optional METALS_API_KEY).", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_polymarket_conflict_odds", "description": "Fetch Polymarket conflict prediction odds.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_metaculus_conflict_questions", "description": "Fetch Metaculus prediction questions relevant to conflict.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_ofac_sanctions_highlights", "description": "Fetch OFAC SDN sanctions highlights for conflict (market/sanctions context).", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
    {"name": "get_tracked_wallet_positions", "description": "Fetch tracked wallet positions from Polymarket.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_tracked_chain_wallets", "description": "Fetch Ethereum balances for tracked addresses (Etherscan).", "input_schema": {"type": "object", "properties": {}}},
]


def enrich_with_ner_entities(
    finint_result: Dict[str, Any],
    entities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Post-processing enrichment: match PERSON/ORG entities from NEWS/SOCMINT NER
    against OFAC keywords. Adds ner_ofac_flags to the FININT result.
    Then runs Document QA on ingested PDF chunks for flagged entities.
    """
    if not entities:
        return finint_result

    ofac_data = finint_result.get("ofac_sanctions", {})
    ofac_sample = ofac_data.get("sample", [])
    ofac_names = {
        entry.get("name", "").lower().strip()
        for entry in ofac_sample
        if entry.get("name")
    }

    flagged: List[Dict[str, Any]] = []
    for ent in entities:
        ent_type = ent.get("type", "")
        if ent_type not in ("PERSON", "ORG"):
            continue
        ent_name = ent.get("entity", "").strip()
        if not ent_name:
            continue
        ent_lower = ent_name.lower()
        for ofac_name in ofac_names:
            if ent_lower in ofac_name or ofac_name in ent_lower:
                flagged.append({
                    "entity": ent_name,
                    "type": ent_type,
                    "ofac_match": ofac_name,
                    "context": ent.get("context", ""),
                })
                break

    finint_result["ner_ofac_flags"] = flagged

    # Document QA enrichment (Phase 4): query PDF chunks for flagged entities
    docqa_results = _docqa_for_flagged_entities(flagged)
    if docqa_results:
        finint_result["docqa_findings"] = docqa_results

    if flagged:
        existing_summary = finint_result.get("summary", "")
        names = ", ".join(f.get("entity", "") for f in flagged[:5])
        docqa_note = ""
        if docqa_results:
            docqa_note = f" DocQA returned {len(docqa_results)} finding(s) from PDF sources."
        finint_result["summary"] = (
            f"{existing_summary} NER-OFAC cross-ref: {len(flagged)} entity match(es) ({names}).{docqa_note}"
        )
    return finint_result


def _docqa_for_flagged_entities(flagged: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    For top flagged entities, run Document QA against ingested OFAC/UN PDFs.
    Uses Haiku first (better reasoning), HF extractive QA as fallback.
    """
    if not flagged:
        return []

    results: List[Dict[str, Any]] = []
    try:
        from services.pdf_ingest_service import find_relevant_chunks, get_all_chunks_for_source
        from services.haiku_service import document_qa as haiku_docqa
        from services.hf_service import document_qa_multi as hf_docqa_multi
    except ImportError:
        return []

    for ent in flagged[:3]:
        entity_name = ent.get("entity", "")
        if not entity_name:
            continue

        question = f"What sanctions, designations, or restrictions apply to {entity_name}?"

        relevant = run_async(find_relevant_chunks(
            question, source="ofac", top_k=5,
        ))
        if not relevant:
            all_ofac = get_all_chunks_for_source("ofac")
            if not all_ofac:
                continue
            chunks = [c for _, c in all_ofac[:10]]
        else:
            chunks = [r.get("text_preview", "") for r in relevant if r.get("text_preview")]

        if not chunks:
            continue

        answer = run_async(haiku_docqa(question, chunks, max_chunks=5))
        if not answer or not answer.get("answer"):
            hf_answers = run_async(hf_docqa_multi(question, chunks, top_k=1))
            if hf_answers:
                answer = hf_answers[0]

        if answer and answer.get("answer"):
            results.append({
                "entity": entity_name,
                "question": question,
                "answer": answer.get("answer", ""),
                "confidence": answer.get("confidence", 0),
                "source": "pdf_docqa",
            })

    return results


def run_finint_agent(conflict: str) -> Dict[str, Any]:
    return run_agent_with_fallback(
        conflict,
        rule_based_fn=_run_rule_based_finint,
        system_prompt=FININT_SYSTEM,
        user_content_template="Analyze financial indicators for conflict: {conflict}",
        tool_fns=_FININT_TOOL_FNS,
        tool_schemas=_FININT_TOOL_SCHEMAS,
    )


