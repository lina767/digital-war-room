"""
FININT Agent – LangChain Tool-Calling Agent
Fetches Brent/WTI oil prices, Polymarket conflict odds, OFAC sanctions highlights, and tracked wallet positions.
- Gamma API: https://gamma-api.polymarket.com (events, markets)
- Data API:  https://data-api.polymarket.com (positions, activity)
- OFAC SDN: Treasury bulk CSV (same source as DIPLO; FININT focus: sanctions/market relevance).
Optional: set POLYMARKET_BUILDER_API_KEY in .env (your personal builder API key) for authenticated requests.
"""
import asyncio
import csv
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import httpx
from .llm import run_tool_agent

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"

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
# Focus: US–Iran, Trump military/foreign policy. 2025-spezifische Märkte entfernt (Stand 2026).
TRACKED_POLYMARKET_SLUGS = [
    "us-strikes-iran-by",
    "will-trump-announce-military-actions-against-iran-by-friday",
    "trump-announces-end-of-military-operations-against-iran-by",
    "trump-invokes-war-powers-against-iran-by",
    "will-trump-visit-china-by",
    "us-x-iran-ceasefire-by",
    "will-the-iranian-regime-fall-by-the-end-of-2026",
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


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _normalize_polymarket_item(m: dict, slug: str = "") -> dict | None:
    """Build {question, probability, volume, url} from Gamma API event or market object."""
    question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
    if not question:
        return None
    prices = m.get("outcomePrices") or []
    prob = 0.0
    if prices:
        prob = max((_safe_float(p) or 0) for p in prices)
    for token in m.get("tokens") or []:
        p = _safe_float(token.get("price"))
        if p and p > prob:
            prob = p
    volume = _safe_float(m.get("volume") or m.get("volumeNum") or m.get("liquidity") or 0) or 0
    url_slug = slug or m.get("slug") or ""
    return {
        "question": question,
        "probability": round(prob, 3),
        "volume": round(volume, 0),
        "url": f"https://polymarket.com/event/{url_slug}" if url_slug else "",
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
        data = asyncio.run(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = _safe_float(latest.get("value"))
        prev_price = _safe_float(prev.get("value"))
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
        data = asyncio.run(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = _safe_float(latest.get("value"))
        prev_price = _safe_float(prev.get("value"))
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
                        v = _safe_float(p)
                        if v and v > prob:
                            prob = v
                    for market in event.get("markets") or []:
                        if not isinstance(market, dict):
                            continue
                        for p in market.get("outcomePrices") or []:
                            v = _safe_float(p)
                            if v and v > prob:
                                prob = v
                        for token in market.get("tokens") or []:
                            v = _safe_float(token.get("price"))
                            if v and v > prob:
                                prob = v
                    volume = _safe_float(
                        event.get("volume") or event.get("volumeNum") or event.get("liquidity") or 0
                    ) or 0
                    out.append({
                        "question": question,
                        "probability": round(prob, 3),
                        "volume": round(volume, 0),
                        "url": f"https://polymarket.com/event/{slug}",
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
        tracked = asyncio.run(_fetch_tracked())
        tracked_questions = {str(t.get("question", ""))[:80] for t in tracked if t.get("question")}

        data = asyncio.run(_fetch_all())
        relevant = []
        seen = set()

        for m in data:
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
            if item:
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
            prob = q.get("community_prediction") or q.get("prob") or q.get("mean")
            if prob is not None:
                prob = _safe_float(prob)
            out.append({
                "title": title[:200],
                "probability": round(prob, 3) if prob is not None else None,
                "url": f"https://www.metaculus.com/questions/{q.get('id', '')}",
                "resolve_time": q.get("resolve_time"),
            })
        return out[:10]

    try:
        return asyncio.run(_fetch())
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
        data = asyncio.run(_fetch())
        if isinstance(data, dict) and "error" in data:
            return data
        rates = (data.get("rates") or {}) if isinstance(data, dict) else {}
        usd = _safe_float(rates.get("USD"))
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
        return asyncio.run(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


def get_ofac_sanctions_highlights(conflict: str) -> Dict[str, Any]:
    """
    Fetch OFAC SDN list and return conflict-relevant sanctions highlights (for markets/finance context).
    Same Treasury CSV as DIPLO; FININT uses this for sanctions exposure and market risk.
    """
    cl = (conflict or "").lower().strip()
    keywords = OFAC_CONFLICT_KEYWORDS.get("default", [])
    for k, v in OFAC_CONFLICT_KEYWORDS.items():
        if k != "default" and k in cl:
            keywords = v
            break

    async def _fetch():
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(OFAC_SDN_CSV_URL)
            resp.raise_for_status()
            return resp.text

    try:
        text = asyncio.run(_fetch())
        reader = csv.DictReader(io.StringIO(text))
        matches: List[Dict[str, Any]] = []
        for row in reader:
            if not row:
                continue
            name = (row.get("name") or (row.get("firstName", "") + " " + row.get("lastName", "")).strip()).lower()
            program = (row.get("programs") or row.get("program", "") or "").lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                matches.append({
                    "name": (row.get("name") or (row.get("firstName", "") + " " + row.get("lastName", "")).strip() or "",
                    "type": row.get("type"),
                    "program": row.get("programs") or row.get("program"),
                })
        return {"total_matches": len(matches), "sample": matches[:15], "error": None}
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e)}


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
                        size = _safe_float(p.get("size") or p.get("tokens") or 0)
                        avg_price = _safe_float(p.get("avgPrice") or p.get("price"))
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
        return asyncio.run(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_finint(conflict: str) -> Dict[str, Any]:
    """Execute FININT tool chain: all tools in parallel. No LLM."""
    tools_to_run = [
        ("brent", get_brent_price, []),
        ("wti", get_wti_price, []),
        ("gold", get_gold_price, []),
        ("polymarket", get_polymarket_conflict_odds, [conflict]),
        ("metaculus", get_metaculus_conflict_questions, [conflict]),
        ("ofac_sanctions", get_ofac_sanctions_highlights, [conflict]),
        ("tracked_wallets", get_tracked_wallet_positions, []),
        ("tracked_chain_wallets", get_tracked_chain_wallets, []),
    ]
    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for key, fn, args in tools_to_run:
            futures[key] = executor.submit(fn, *args) if args else executor.submit(fn)
        for key in futures:
            try:
                results[key] = futures[key].result(timeout=30)
            except Exception as e:
                results[key] = {"error": str(e)} if key in ("brent", "wti", "gold") else [{"error": str(e)}]

    brent = results.get("brent") or {}
    wti = results.get("wti") or {}
    gold = results.get("gold") or {}
    polymarket = results.get("polymarket")
    metaculus = results.get("metaculus")
    ofac_sanctions = results.get("ofac_sanctions") or {}
    tracked_wallets = results.get("tracked_wallets")
    tracked_chain_wallets = results.get("tracked_chain_wallets")

    if not isinstance(polymarket, list):
        polymarket = []
    if not isinstance(tracked_wallets, list):
        tracked_wallets = []
    if not isinstance(metaculus, list):
        metaculus = []
    if not isinstance(tracked_chain_wallets, list):
        tracked_chain_wallets = []

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
    if polymarket:
        max_prob = max((_safe_float(p.get("probability")) or 0) for p in polymarket if isinstance(p, dict) and "error" not in p)
        if max_prob and max_prob > 0.5:
            base += 20
        elif max_prob and max_prob > 0.3:
            base += 10
    if metaculus:
        meta_probs = [_safe_float(p.get("probability")) for p in metaculus if isinstance(p, dict) and "error" not in p and p.get("probability") is not None]
        if meta_probs:
            max_meta = max(meta_probs)
            if max_meta and max_meta > 0.5:
                base += 8
            elif max_meta and max_meta > 0.3:
                base += 4
    ofac_total = (int(ofac_sanctions.get("total_matches") or 0) if isinstance(ofac_sanctions, dict) and "error" not in ofac_sanctions else 0)
    if ofac_total > 200:
        base += 6
    elif ofac_total > 50:
        base += 3
    score = max(0.0, min(100.0, base))

    return {
        "brent": brent if isinstance(brent, dict) and "error" not in brent else {"price": None, "change_pct": "0.0%", "as_of": ""},
        "wti": wti if isinstance(wti, dict) and "error" not in wti else {"price": None, "change_pct": "0.0%", "as_of": ""},
        "gold": gold if isinstance(gold, dict) and "error" not in gold else {"price": None, "change_pct": "0.0%", "as_of": ""},
        "polymarket": [p for p in polymarket if isinstance(p, dict) and "error" not in p],
        "metaculus": [m for m in metaculus if isinstance(m, dict) and "error" not in m],
        "ofac_sanctions": ofac_sanctions if isinstance(ofac_sanctions, dict) and "error" not in ofac_sanctions else {"total_matches": 0, "sample": [], "error": (ofac_sanctions.get("error") if isinstance(ofac_sanctions, dict) else (ofac_sanctions[0].get("error") if isinstance(ofac_sanctions, list) and ofac_sanctions else None))},
        "tracked_wallets": [w for w in tracked_wallets if isinstance(w, dict)],
        "tracked_chain_wallets": [w for w in tracked_chain_wallets if isinstance(w, dict) and "balance_eth" in w],
        "escalation_score": round(score, 1),
        "summary": "FININT (rule-based): oil, gold, Polymarket, Metaculus, OFAC sanctions highlights, and wallet data from fixed tool chain.",
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


def run_finint_agent(conflict: str) -> Dict[str, Any]:
    """Run FININT: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_finint(conflict)

    TOOL_FNS = {
        "get_brent_price": get_brent_price,
        "get_wti_price": get_wti_price,
        "get_gold_price": get_gold_price,
        "get_polymarket_conflict_odds": get_polymarket_conflict_odds,
        "get_metaculus_conflict_questions": get_metaculus_conflict_questions,
        "get_ofac_sanctions_highlights": get_ofac_sanctions_highlights,
        "get_tracked_wallet_positions": get_tracked_wallet_positions,
        "get_tracked_chain_wallets": get_tracked_chain_wallets,
    }
    TOOL_SCHEMAS = [
        {"name": "get_brent_price", "description": "Fetch current Brent crude oil price from Alpha Vantage.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_wti_price", "description": "Fetch current WTI crude oil price from Alpha Vantage.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_gold_price", "description": "Fetch current gold (XAU) price in USD (optional METALS_API_KEY).", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_polymarket_conflict_odds", "description": "Fetch Polymarket conflict prediction odds.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_metaculus_conflict_questions", "description": "Fetch Metaculus prediction questions relevant to conflict.", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_ofac_sanctions_highlights", "description": "Fetch OFAC SDN sanctions highlights for conflict (market/sanctions context).", "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]}},
        {"name": "get_tracked_wallet_positions", "description": "Fetch tracked wallet positions from Polymarket.", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_tracked_chain_wallets", "description": "Fetch Ethereum balances for tracked addresses (Etherscan).", "input_schema": {"type": "object", "properties": {}}},
    ]
    text = run_tool_agent(
        system=FININT_SYSTEM,
        user_content=f"Analyze financial indicators for conflict: {conflict}",
        tool_fns=TOOL_FNS,
        tool_schemas=TOOL_SCHEMAS,
    )
    if text:
        text = text.strip()
        for prefix in ("```json", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except Exception:
            pass
    return _run_rule_based_finint(conflict)


