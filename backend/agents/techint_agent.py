"""
TECHINT Agent – Tech sector indicators, export control, IODA, OONI, Cloudflare Radar, Shodan.
Fetches: tech ETF quotes (Alpha Vantage), export-control news (NewsAPI), IODA v2 API
(outages, BGP/signals raw, alerts, entities/ASNs), OONI, Cloudflare Radar, Shodan.
IODA: https://api.ioda.inetintel.cc.gatech.edu/v2/ — BGP routing anomalies, internet outages.
"""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .utils import run_async

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
NEWS_API_URL = "https://newsapi.org/v2/everything"
# IODA v2 API – outages, signals (BGP/Ping/Telescope), alerts, entities (ASNs)
IODA_BASE = "https://api.ioda.inetintel.cc.gatech.edu/v2"
OONI_MEASUREMENTS_URL = "https://api.ooni.io/api/v1/measurements"
CLOUDFLARE_RADAR_OUTAGES_URL = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
SHODAN_HOST_COUNT_URL = "https://api.shodan.io/shodan/host/count"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
RDAP_DOMAIN_URL = "https://rdap.org/domain"
GOOGLE_DNS_RESOLVE_URL = "https://dns.google/resolve"

# URLs to check in Wayback Machine per conflict (detect deletions). Expand as needed.
WAYBACK_URLS_BY_CONFLICT: Dict[str, List[str]] = {
    "iran": ["https://www.state.gov/", "https://www.whitehouse.gov/", "https://en.wikipedia.org/wiki/Iran"],
    "us-iran": ["https://www.state.gov/", "https://www.whitehouse.gov/"],
    "ukraine": ["https://www.president.gov.ua/", "https://en.wikipedia.org/wiki/2022_Russian_invasion_of_Ukraine"],
    "russia": ["https://en.wikipedia.org/wiki/Russia"],
}

# Shodan: strategic port counts (no search credits; count API is free)
# Industrial/SCADA: 502 Modbus, 44818 EtherNet/IP, 47808 BACnet, 1911 Tridium Niagara, 102 Siemens S7
# General: 22 SSH, 443 HTTPS
SHODAN_PORT_QUERIES = [
    (502, "port:502", "industrial_modbus"),
    (44818, "port:44818", "industrial_ethernet_ip"),  # Rockwell EtherNet/IP
    (47808, "port:47808", "industrial_bacnet"),       # BACnet building automation
    (1911, "port:1911", "industrial_niagara"),       # Tridium Niagara
    (102, "port:102", "industrial_s7"),               # Siemens S7
    (22, "port:22", "ssh"),
    (443, "port:443", "https"),
]

# OONI: test names for Telegram and Signal blocking detection
OONI_INSTANT_MESSAGING_TESTS = ["telegram", "signal"]

# Conflict keyword -> ISO 3166-1 alpha-2 country code(s) for IODA/Radar
CONFLICT_COUNTRY_CODES: Dict[str, List[str]] = {
    "iran": ["IR"],
    "us-iran": ["IR", "US"],
    "russia": ["RU"],
    "ukraine": ["UA"],
    "israel": ["IL"],
    "gaza": ["PS"],
    "lebanon": ["LB"],
    "china": ["CN"],
    "taiwan": ["TW"],
    "syria": ["SY"],
    "yemen": ["YE"],
    "iraq": ["IQ"],
    "afghanistan": ["AF"],
}

# Tech/semiconductor proxies for supply-chain and sanctions sensitivity
TECH_SYMBOLS = [
    ("SMH", "Semiconductor ETF"),
    ("QQQ", "Nasdaq-100 / Tech"),
]

# Conflict → domains to track in WHOIS/DNS (infrastructure attribution, registrars, DNS changes)
WHOIS_DOMAINS_BY_CONFLICT: Dict[str, List[str]] = {
    "iran": [
        "leader.ir",
        "president.ir",
        "irib.ir",
    ],
    "us-iran": [
        "state.gov",
        "centcom.mil",
    ],
    "ukraine": [
        "president.gov.ua",
        "mil.gov.ua",
    ],
    "russia": [
        "mil.ru",
        "kremlin.ru",
    ],
}

EXPORT_CONTROL_QUERY = (
    '"export control" OR "export controls" OR "semiconductor sanctions" '
    'OR "chip export" OR "BIS entity list" OR "technology sanctions" '
    'OR "dual-use" OR "restricted technology"'
)
NEWS_DOMAINS = (
    "reuters.com,apnews.com,bbc.com,theguardian.com,ft.com,bloomberg.com,"
    "politico.com,defensenews.com,reuters.com,wsj.com,cnbc.com,techcrunch.com"
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _conflict_to_country_codes(conflict: str) -> List[str]:
    """Map conflict string to IODA/Radar country codes (ISO 3166-1 alpha-2)."""
    cl = (conflict or "").lower().strip()
    for key, codes in CONFLICT_COUNTRY_CODES.items():
        if key in cl:
            return list(codes)
    return []


def _ioda_time_range(days: int = 7) -> tuple[int, int]:
    """Return (from_ts, until_ts) for IODA API (Unix seconds)."""
    until_ts = int(time.time())
    from_ts = until_ts - (days * 24 * 3600)
    return from_ts, until_ts


async def _fetch_ioda_outages(client: httpx.AsyncClient, entity_code: str, from_ts: int, until_ts: int, limit: int = 10) -> List[Dict[str, Any]]:
    """GET /v2/outages/events — outage events for country (entityType, entityCode, from, until)."""
    try:
        resp = await client.get(
            f"{IODA_BASE}/outages/events",
            params={
                "entityType": "country",
                "entityCode": entity_code,
                "from": from_ts,
                "until": until_ts,
                "limit": limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(items, list):
            return []
        return [{"entityCode": entity_code, "location": x.get("location"), "start": x.get("start"), "duration": x.get("duration"), "datasource": x.get("datasource"), **(x if isinstance(x, dict) else {})} for x in items[:limit]]
    except Exception as e:
        return [{"entityCode": entity_code, "error": str(e)}]


async def _fetch_ioda_signals_raw(client: httpx.AsyncClient, entity_code: str, from_ts: int, until_ts: int) -> Dict[str, Any]:
    """GET /v2/signals/raw/country/{code} — BGP, Active Probing (Ping), Telescope time-series."""
    try:
        resp = await client.get(
            f"{IODA_BASE}/signals/raw/country/{entity_code}",
            params={"from": from_ts, "until": until_ts},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return {"entityCode": entity_code, "signals": {}}
        # API may return nested by datasource (BGP, ping, telescope)
        signals = data.get("signals") or data.get("data") or data
        return {"entityCode": entity_code, "signals": signals, "from": from_ts, "until": until_ts}
    except Exception as e:
        return {"entityCode": entity_code, "error": str(e), "signals": {}}


async def _fetch_ioda_alerts(client: httpx.AsyncClient, entity_code: str, from_ts: int, until_ts: int) -> List[Dict[str, Any]]:
    """Fetch anomaly alerts (same /outages/events with includeAlerts=true for BGP/signal-deviation alerts)."""
    try:
        resp = await client.get(
            f"{IODA_BASE}/outages/events",
            params={
                "entityType": "country",
                "entityCode": entity_code,
                "from": from_ts,
                "until": until_ts,
                "includeAlerts": "true",
                "limit": 20,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(items, list):
            return []
        return [{"entityCode": entity_code, "type": "alert", **(x if isinstance(x, dict) else {})} for x in items]
    except Exception as e:
        return [{"entityCode": entity_code, "error": str(e)}]


async def _fetch_ioda_entities(client: httpx.AsyncClient, entity_code: str) -> List[Dict[str, Any]]:
    """GET /v2/entities/query — ASNs in country (e.g. Irancell, TCI). relatedTo=country/IR."""
    try:
        resp = await client.get(
            f"{IODA_BASE}/entities/query",
            params={"entityType": "asn", "relatedTo": f"country/{entity_code}"},
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(items, list):
            return []
        return [{"entityCode": entity_code, **(x if isinstance(x, dict) else {})} for x in items[:50]]
    except Exception as e:
        return [{"entityCode": entity_code, "error": str(e)}]


async def _fetch_ioda_all(conflict: str) -> Dict[str, Any]:
    """
    Fetch IODA v2: outages, signals (BGP/Ping/Telescope), alerts, entities for conflict countries.
    Returns unified structure; ioda_events = combined list for backward compat (outages + alerts).
    """
    codes = _conflict_to_country_codes(conflict)
    if not codes:
        return {"outages": [], "signals_raw": [], "alerts": [], "entities": [], "ioda_events": []}
    from_ts, until_ts = _ioda_time_range(7)
    outages: List[Dict[str, Any]] = []
    signals_raw: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=25.0) as client:
        for entity_code in codes[:3]:
            out = await _fetch_ioda_outages(client, entity_code, from_ts, until_ts, limit=10)
            outages.extend(out)
            sig = await _fetch_ioda_signals_raw(client, entity_code, from_ts, until_ts)
            if "error" not in sig:
                signals_raw.append(sig)
            al = await _fetch_ioda_alerts(client, entity_code, from_ts, until_ts)
            alerts.extend(al)
            ent = await _fetch_ioda_entities(client, entity_code)
            entities.extend(ent)
    # Backward compat: ioda_events = outages + alerts (each with entityCode)
    ioda_events: List[Dict[str, Any]] = []
    for o in outages:
        if "error" not in o:
            ioda_events.append({"entityCode": o.get("entityCode"), "type": "outage", **o})
    for a in alerts:
        if "error" not in a:
            ioda_events.append({"entityCode": a.get("entityCode"), "type": "alert", **a})
    return {
        "outages": outages,
        "signals_raw": signals_raw,
        "alerts": alerts,
        "entities": entities,
        "ioda_events": ioda_events,
    }


async def _fetch_ooni_measurements(conflict: str) -> Dict[str, Any]:
    """
    Fetch OONI measurements for Telegram/Signal in conflict-relevant countries.
    If Telegram or Signal appear as confirmed_blocked in Iran (IR) → escalation indicator.
    API: https://api.ooni.io/api/v1/
    """
    codes = _conflict_to_country_codes(conflict)
    if not codes:
        return {"measurements": [], "confirmed_blocked": [], "telegram_signal_blocked_iran": False}
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    confirmed_blocked: List[Dict[str, Any]] = []
    all_measurements: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            for probe_cc in codes[:3]:
                for test_name in OONI_INSTANT_MESSAGING_TESTS:
                    try:
                        resp = await client.get(
                            OONI_MEASUREMENTS_URL,
                            params={
                                "probe_cc": probe_cc,
                                "test_name": test_name,
                                "since": since,
                                "limit": 50,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        results = data.get("results") or []
                        for r in results:
                            all_measurements.append({
                                "probe_cc": probe_cc,
                                "test_name": test_name,
                                "measurement_id": r.get("measurement_id"),
                                "input": r.get("input"),
                                "anomaly": r.get("anomaly"),
                                "confirmed": r.get("confirmed"),
                            })
                            # Check for confirmed_blocked (can be in r.confirmed or inside measurement)
                            is_confirmed_blocked = (
                                r.get("confirmed") is True
                                or (isinstance(r.get("confirmed"), str) and "blocked" in str(r.get("confirmed")).lower())
                            )
                            if is_confirmed_blocked:
                                confirmed_blocked.append({
                                    "probe_cc": probe_cc,
                                    "test_name": test_name,
                                    "measurement_id": r.get("measurement_id"),
                                })
                    except Exception as e:
                        all_measurements.append({"probe_cc": probe_cc, "test_name": test_name, "error": str(e)})
    except Exception as e:
        return {"measurements": [], "confirmed_blocked": [], "telegram_signal_blocked_iran": False, "error": str(e)}
    telegram_signal_blocked_iran = any(
        c.get("probe_cc") == "IR" for c in confirmed_blocked
    )
    return {
        "measurements": all_measurements[:30],
        "confirmed_blocked": confirmed_blocked,
        "telegram_signal_blocked_iran": telegram_signal_blocked_iran,
    }


async def _fetch_cloudflare_outages(token: str, conflict: str) -> List[Dict[str, Any]]:
    """Fetch Cloudflare Radar outage annotations (e.g. internet shutdowns). Last 7 days."""
    codes = _conflict_to_country_codes(conflict)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                CLOUDFLARE_RADAR_OUTAGES_URL,
                params={"limit": 20, "offset": 0, "dateRange": "7d", "format": "json"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        result = data.get("result") or {}
        annotations = result.get("annotations") or []
        # Optionally filter by conflict-relevant locations
        if codes:
            filtered = [a for a in annotations if a.get("locations") and any(loc in (a.get("locations") or []) for loc in codes)]
            if filtered:
                return filtered[:10]
        return list(annotations)[:10]
    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_shodan_activity(api_key: str, conflict: str) -> Dict[str, Any]:
    """
    Shodan host count for conflict-relevant countries (count API uses no query credits).
    Breakdown by strategic ports: industrial (502 Modbus, 44818 EtherNet/IP, 47808 BACnet, 1911 Niagara, 102 S7), SSH, HTTPS.
    Industrial/SCADA exposure in conflict zone = escalation indicator.
    """
    codes = _conflict_to_country_codes(conflict)
    if not codes or not api_key:
        return {"countries": [], "total_count": 0, "port_breakdown": {}, "industrial_exposed": 0}
    countries: List[Dict[str, Any]] = []
    total = 0
    port_breakdown: Dict[str, int] = {}
    industrial_exposed = 0
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for cc in codes[:3]:
                try:
                    resp = await client.get(
                        SHODAN_HOST_COUNT_URL,
                        params={"key": api_key, "query": f"country:{cc}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    c = int(data.get("total", 0))
                    total += c
                    country_data: Dict[str, Any] = {"country": cc, "count": c, "ports": {}}
                    for port_num, port_query, label in SHODAN_PORT_QUERIES:
                        try:
                            r = await client.get(
                                SHODAN_HOST_COUNT_URL,
                                params={"key": api_key, "query": f"country:{cc} {port_query}"},
                            )
                            r.raise_for_status()
                            port_count = int(r.json().get("total", 0))
                            country_data["ports"][str(port_num)] = port_count
                            port_breakdown[label] = port_breakdown.get(label, 0) + port_count
                            if port_num in (502, 44818, 47808, 1911, 102):
                                industrial_exposed += port_count
                        except Exception:
                            country_data["ports"][str(port_num)] = 0
                    countries.append(country_data)
                except Exception as e:
                    countries.append({"country": cc, "error": str(e)})
            # Optional: has_vuln count for first country (attack surface indicator)
            vuln_count: int | None = None
            if codes:
                try:
                    r = await client.get(
                        SHODAN_HOST_COUNT_URL,
                        params={"key": api_key, "query": f"country:{codes[0]} has_vuln:1"},
                    )
                    r.raise_for_status()
                    vuln_count = int(r.json().get("total", 0))
                except Exception:
                    pass
        out: Dict[str, Any] = {
            "countries": countries,
            "total_count": total,
            "port_breakdown": port_breakdown,
            "industrial_exposed": industrial_exposed,
        }
        if vuln_count is not None:
            out["vuln_count"] = vuln_count
        return out
    except Exception as e:
        return {"countries": [], "total_count": 0, "port_breakdown": {}, "industrial_exposed": 0, "error": str(e)}


async def _fetch_wayback_snapshots(conflict: str) -> Dict[str, Any]:
    """
    Query Archive.org CDX for configured URLs per conflict. Returns snapshot count and last capture per URL.
    No API key required for CDX search. Use to detect if official/News pages were changed or removed.
    """
    cl = (conflict or "").lower().strip()
    urls = []
    for key, list_urls in WAYBACK_URLS_BY_CONFLICT.items():
        if key in cl:
            urls = list_urls
            break
    if not urls:
        return {"urls_checked": [], "snapshots": [], "summary": "No Wayback URLs configured for this conflict."}

    result: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            for url in urls[:10]:
                try:
                    resp = await client.get(
                        WAYBACK_CDX_URL,
                        params={"url": url, "output": "json", "limit": 5, "collapse": "timestamp:6"},
                    )
                    if resp.status_code != 200:
                        result.append({"url": url, "error": resp.status_code})
                        continue
                    data = resp.json()
                    if not isinstance(data, list) or len(data) < 2:
                        result.append({"url": url, "snapshot_count": 0, "last_capture": None})
                        continue
                    # First row is header; rows are [urlkey, timestamp, original, ...]
                    rows = data[1:]
                    last_ts = rows[0][1] if rows else None
                    result.append({
                        "url": url,
                        "snapshot_count": len(rows),
                        "last_capture": last_ts,
                        "wayback_url": f"https://web.archive.org/web/{last_ts}/{url}" if last_ts else None,
                    })
                except Exception as e:
                    result.append({"url": url, "error": str(e)})
        return {
            "urls_checked": urls[:10],
            "snapshots": result,
            "summary": f"Wayback: {len([r for r in result if 'error' not in r])} URL(s) checked.",
        }
    except Exception as e:
        return {"urls_checked": [], "snapshots": [], "summary": "", "error": str(e)}


async def _fetch_whois_dns(conflict: str) -> Dict[str, Any]:
    """
    Fetch WHOIS (via RDAP) and DNS A-records (via Google DNS over HTTPS) for
    conflict-relevant domains. No API key required.
    """
    cl = (conflict or "").lower().strip()
    domains: List[str] = []
    for key, ds in WHOIS_DOMAINS_BY_CONFLICT.items():
        if key in cl:
            domains = ds
            break
    if not domains:
        return {
            "domains": [],
            "results": [],
            "summary": "No WHOIS domains configured for this conflict.",
        }

    results: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for domain in domains:
                item: Dict[str, Any] = {"domain": domain}
                # WHOIS / RDAP
                try:
                    resp = await client.get(f"{RDAP_DOMAIN_URL}/{domain}")
                    if resp.status_code == 200:
                        data = resp.json()
                        registrar = data.get("registrar") or data.get("registrarName")
                        if not registrar:
                            # Try entities role=registrar
                            for ent in data.get("entities") or []:
                                if not isinstance(ent, dict):
                                    continue
                                roles = ent.get("roles") or []
                                if "registrar" in roles:
                                    vcard = ent.get("vcardArray") or []
                                    if len(vcard) == 2 and isinstance(vcard[1], list):
                                        for field in vcard[1]:
                                            if isinstance(field, list) and len(field) >= 4 and field[0] == "fn":
                                                registrar = field[3]
                                                break
                                if registrar:
                                    break
                        created = None
                        expires = None
                        for ev in data.get("events") or []:
                            if not isinstance(ev, dict):
                                continue
                            action = (ev.get("eventAction") or "").lower()
                            if action in ("registration", "registered", "create"):
                                created = ev.get("eventDate")
                            elif action in ("expiration", "expiry", "expire"):
                                expires = ev.get("eventDate")
                        item["whois"] = {
                            "registrar": registrar,
                            "created": created,
                            "expires": expires,
                        }
                    else:
                        item["whois_error"] = resp.status_code
                except Exception as e:  # pragma: no cover - network failure path
                    item["whois_error"] = str(e)

                # DNS A-records via Google Public DNS
                try:
                    dns_resp = await client.get(
                        GOOGLE_DNS_RESOLVE_URL,
                        params={"name": domain, "type": "A"},
                    )
                    if dns_resp.status_code == 200:
                        dns_data = dns_resp.json()
                        answers = dns_data.get("Answer") or []
                        item["dns_a"] = [
                            a.get("data")
                            for a in answers
                            if isinstance(a, dict) and a.get("type") == 1 and a.get("data")
                        ]
                    else:
                        item["dns_error"] = dns_resp.status_code
                except Exception as e:  # pragma: no cover - network failure path
                    item.setdefault("dns_error", str(e))

                results.append(item)

        ok = [r for r in results if r.get("whois") or r.get("dns_a")]
        summary = (
            f"WHOIS/DNS: {len(ok)} domain(s) resolved."
            if ok
            else "WHOIS/DNS: no successful lookups."
        )
        return {"domains": domains, "results": results, "summary": summary}
    except Exception as e:  # pragma: no cover - network failure path
        return {"domains": domains, "results": [], "summary": "", "error": str(e)}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str, api_key: str) -> Dict[str, Any]:
    """Fetch GLOBAL_QUOTE for one symbol."""
    try:
        resp = await client.get(ALPHAVANTAGE_URL, params={
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        }, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        q = data.get("Global Quote") or {}
        price = _safe_float(q.get("05. price"))
        prev = _safe_float(q.get("08. previous close"))
        change_pct = ((price - prev) / prev * 100) if prev and prev != 0 else None
        return {
            "symbol": symbol,
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "change_pct_raw": change_pct,
            "as_of": q.get("07. latest trading day", ""),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "price": None, "change_pct": "0.0%", "change_pct_raw": None}


async def _fetch_tech_indicators(api_key: str) -> List[Dict[str, Any]]:
    """Fetch quotes for all TECH_SYMBOLS."""
    results = []
    async with httpx.AsyncClient() as client:
        for symbol, _ in TECH_SYMBOLS:
            r = await _fetch_quote(client, symbol, api_key)
            r["label"] = next((l for s, l in TECH_SYMBOLS if s == symbol), symbol)
            results.append(r)
    return results


async def _fetch_export_control_news(api_key: str, conflict: str) -> List[Dict[str, Any]]:
    """Search NewsAPI for export control / tech sanctions articles."""
    try:
        from_date = datetime.now(timezone.utc) - timedelta(hours=72)
        query = f"({EXPORT_CONTROL_QUERY})"
        # Optionally narrow by conflict
        cl = (conflict or "").lower()
        if "china" in cl or "iran" in cl or "russia" in cl:
            query = f"{query} AND ({conflict})"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "relevance",
            "pageSize": 15,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "domains": NEWS_DOMAINS,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NEWS_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        articles = []
        for art in data.get("articles", []):
            title = (art.get("title") or "").strip()
            if not title:
                continue
            source = (art.get("source") or {}).get("name") or ""
            articles.append({
                "title": title,
                "source": source,
                "url": art.get("url"),
                "published_at": art.get("publishedAt"),
                "description": (art.get("description") or "")[:200],
            })
        return articles
    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_wigle_networks(conflict: str) -> Dict[str, Any]:
    """
    Query Wigle.net WiFi database for conflict-relevant region (bounding box).
    Auth: WIGLE_API_TOKEN (required). If it contains ":", use as username:token; else use WIGLE_API_NAME + WIGLE_API_TOKEN.
    """
    raw_token = (os.getenv("WIGLE_API_TOKEN") or "").strip()
    if ":" in raw_token:
        username, token = raw_token.split(":", 1)
        username, token = username.strip(), token.strip()
    else:
        username = (os.getenv("WIGLE_API_NAME") or "").strip()
        token = raw_token
    cl = (conflict or "").lower().strip()
    # Simple coarse bounding boxes per conflict (lat1, lat2, lon1, lon2)
    wigle_bbox_by_conflict: Dict[str, tuple[float, float, float, float]] = {
        "iran": (24.0, 40.0, 44.0, 63.0),
        "us-iran": (24.0, 40.0, 44.0, 63.0),
        "ukraine": (44.0, 53.0, 22.0, 41.0),
        "russia": (54.0, 71.0, 30.0, 150.0),
    }
    bbox = None
    for key, box in wigle_bbox_by_conflict.items():
        if key in cl:
            bbox = box
            break
    if not username or not token or not bbox:
        return {"total_results": 0, "sample": [], "error": "Wigle API not configured or no bbox for conflict."}

    lat1, lat2, lon1, lon2 = bbox
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            auth=httpx.BasicAuth(username, token),
        ) as client:
            resp = await client.get(
                "https://api.wigle.net/api/v2/network/search",
                params={
                    "latrange1": lat1,
                    "latrange2": lat2,
                    "longrange1": lon1,
                    "longrange2": lon2,
                    "resultsPerPage": 50,
                    "page": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        sample = []
        for r in results[:30]:
            if not isinstance(r, dict):
                continue
            sample.append(
                {
                    "ssid": r.get("ssid"),
                    "netid": r.get("netid"),
                    "trilat": r.get("trilat"),
                    "trilong": r.get("trilong"),
                    "encryption": r.get("encryption"),
                    "lasttime": r.get("lasttime"),
                }
            )
        total = data.get("totalResults") or data.get("total", len(results))
        return {"total_results": int(total or 0), "sample": sample}
    except Exception as e:  # pragma: no cover - network failure path
        return {"total_results": 0, "sample": [], "error": str(e)}


def _compute_techint_score(
    tech_indicators: List[Dict],
    export_articles: List[Dict],
    ioda_events: List[Dict],
    ooni_result: Dict[str, Any],
    cloudflare_outages: List[Dict],
    shodan_activity: Dict[str, Any],
    whois_dns: Dict[str, Any] | None = None,
    wigle_result: Dict[str, Any] | None = None,
) -> float:
    """Compute TECHINT escalation score 0–100 from all signals."""
    base = 30.0
    # Tech sell-off
    for ind in tech_indicators:
        raw = ind.get("change_pct_raw")
        if raw is not None and raw < -3:
            base += 12
        elif raw is not None and raw < 0:
            base += 5
    # Export control news
    valid_articles = [a for a in export_articles if "error" not in a]
    if len(valid_articles) >= 5:
        base += 25
    elif len(valid_articles) >= 2:
        base += 15
    elif len(valid_articles) >= 1:
        base += 8
    # IODA internet outage events
    valid_ioda = [e for e in ioda_events if "error" not in e]
    if len(valid_ioda) >= 3:
        base += 18
    elif len(valid_ioda) >= 1:
        base += 10
    # OONI: Telegram + Signal confirmed_blocked in Iran = strong escalation indicator
    if ooni_result.get("telegram_signal_blocked_iran"):
        base += 22
    elif ooni_result.get("confirmed_blocked"):
        base += 12
    # Cloudflare Radar outages in conflict region
    valid_cf = [o for o in cloudflare_outages if "error" not in o]
    if len(valid_cf) >= 3:
        base += 15
    elif len(valid_cf) >= 1:
        base += 8
    # Shodan: host count + industrial/SCADA exposure (port 502) in conflict zone
    total_shodan = int(shodan_activity.get("total_count") or 0)
    industrial = int(shodan_activity.get("industrial_exposed") or 0)
    vuln_count = shodan_activity.get("vuln_count")
    if total_shodan > 500000:
        base += 5
    if industrial > 500:
        base += 12   # Exposed industrial/SCADA in conflict zone = strong escalation
    elif industrial > 100:
        base += 8
    elif industrial > 0:
        base += 4
    if vuln_count is not None and int(vuln_count) > 20000:
        base += 5   # Large attack surface in region
    # Light touch: if WHOIS/DNS/Wigle have data, nudge score slightly (signals active infrastructure mapping)
    if whois_dns and isinstance(whois_dns, dict) and whois_dns.get("results"):
        base += 2
    if wigle_result and isinstance(wigle_result, dict) and (wigle_result.get("total_results") or 0) > 0:
        base += 2
    return min(100.0, max(0.0, base))


def _build_summary(
    tech_indicators: List[Dict],
    export_articles: List[Dict],
    ioda_events: List[Dict],
    ioda_result: Dict[str, Any],
    ooni_result: Dict[str, Any],
    cloudflare_outages: List[Dict],
    shodan_activity: Dict[str, Any],
    techint_score: float,
    wayback_result: Dict[str, Any] | None = None,
    whois_dns: Dict[str, Any] | None = None,
    wigle_result: Dict[str, Any] | None = None,
) -> str:
    """One- or two-sentence summary."""
    valid_tech = [t for t in tech_indicators if t.get("price") and "error" not in t]
    valid_news = [a for a in export_articles if "error" not in a]
    valid_ioda = [e for e in ioda_events if "error" not in e]
    valid_cf = [o for o in cloudflare_outages if "error" not in o]
    parts = []
    if valid_tech:
        moves = [f"{t['symbol']} {t['change_pct']}" for t in valid_tech]
        parts.append(f"Tech: {', '.join(moves)}.")
    if valid_news:
        parts.append(f"Export control: {len(valid_news)} articles.")
    if valid_ioda:
        outages_n = len([x for x in (ioda_result.get("outages") or []) if "error" not in x])
        alerts_n = len([x for x in (ioda_result.get("alerts") or []) if "error" not in x])
        signals_n = len(ioda_result.get("signals_raw") or [])
        entities_n = len([x for x in (ioda_result.get("entities") or []) if "error" not in x])
        msg = f"IODA: {len(valid_ioda)} event(s) (outages/alerts)."
        if outages_n or alerts_n:
            msg = f"IODA: {outages_n} outage(s), {alerts_n} alert(s)."
        if signals_n:
            msg += f" BGP/Ping/Telescope signals for {signals_n} country/codes."
        if entities_n:
            msg += f" {entities_n} ASN(s) in region."
        parts.append(msg)
    if ooni_result.get("telegram_signal_blocked_iran"):
        parts.append("OONI: Telegram/Signal confirmed blocked in Iran (escalation).")
    elif ooni_result.get("confirmed_blocked"):
        parts.append(f"OONI: {len(ooni_result.get('confirmed_blocked', []))} confirmed_blocked.")
    if valid_cf:
        parts.append(f"Cloudflare Radar: {len(valid_cf)} outage(s).")
    if shodan_activity.get("total_count") or shodan_activity.get("industrial_exposed"):
        total_s = shodan_activity.get("total_count", 0)
        ind = shodan_activity.get("industrial_exposed", 0)
        vuln_s = shodan_activity.get("vuln_count")
        msg = f"Shodan: {total_s} hosts in region."
        if ind > 0:
            msg += f" {ind} industrial/SCADA (Modbus, EtherNet/IP, BACnet, etc.) exposed."
        if vuln_s is not None:
            msg += f" {vuln_s} with known vulns (primary country)."
        parts.append(msg)
    if wayback_result and wayback_result.get("snapshots"):
        n = len([s for s in wayback_result.get("snapshots") or [] if "error" not in s])
        if n:
            parts.append(f"Wayback: {n} URL(s) checked for archives.")
    if whois_dns and whois_dns.get("results"):
        parts.append(f"WHOIS/DNS: {len(whois_dns.get('results') or [])} domain(s) queried.")
    if wigle_result and isinstance(wigle_result, dict) and (wigle_result.get("total_results") or 0) > 0:
        parts.append(f"Wigle: {wigle_result.get('total_results', 0)} WiFi networks in region (sample stored).")
    if not parts:
        return "TECHINT: No tech, export control, IODA, OONI, Cloudflare, or Shodan data."
    return "TECHINT: " + " ".join(parts)


async def _generate_haiku_summary_techint(
    conflict: str,
    tech_indicators: List[Dict],
    export_controls: List[Dict],
    ioda_events: List[Dict],
    ioda_result: Dict[str, Any],
    ooni_result: Dict[str, Any],
    cloudflare_outages: List[Dict],
    shodan_activity: Dict[str, Any],
    techint_score: float,
) -> Optional[str]:
    """Optional 2-3 sentence analyst summary via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary
        compact = {
            "conflict": conflict,
            "techint_score": techint_score,
            "tech_etfs": [{"symbol": t.get("symbol"), "change_pct": t.get("change_pct")} for t in (tech_indicators or [])[:5] if t.get("symbol")],
            "export_control_articles": len([a for a in (export_controls or []) if "error" not in a]),
            "ioda_outages": len(ioda_result.get("outages") or []),
            "ioda_alerts": len(ioda_result.get("alerts") or []),
            "ooni_telegram_blocked": ooni_result.get("telegram_signal_blocked_iran"),
            "cloudflare_outages": len(cloudflare_outages or []),
            "shodan_hosts": shodan_activity.get("total_count"),
            "shodan_industrial": shodan_activity.get("industrial_exposed"),
        }
        import json
        data = json.dumps(compact, indent=2)
        system = (
            "You are a tech and export-control analyst for conflict monitoring. Summarize the following "
            "TECHINT data in 2-3 sentences: tech ETFs, export control news, IODA outages, OONI blocks, "
            "Cloudflare Radar, Shodan. Focus on escalation signals. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256)
        return out.strip() if out else None
    except Exception:
        return None


def run_techint_agent(conflict: str) -> Dict[str, Any]:
    """Run TECHINT: tech indicators, export control, IODA, OONI, Cloudflare Radar, Shodan."""
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")
    news_key = os.getenv("NEWS_API_KEY")
    cf_token = os.getenv("CLOUDFLARE_RADAR_API_TOKEN")
    shodan_key = os.getenv("SHODAN_API_KEY")

    async def _run() -> Dict[str, Any]:
        tech_indicators = await _fetch_tech_indicators(av_key) if av_key else []
        export_controls = await _fetch_export_control_news(news_key, conflict) if news_key else []
        ioda_result = await _fetch_ioda_all(conflict)
        ioda_events = ioda_result.get("ioda_events") or []
        ooni_result = await _fetch_ooni_measurements(conflict)
        cloudflare_outages = await _fetch_cloudflare_outages(cf_token, conflict) if cf_token else []
        shodan_activity = await _fetch_shodan_activity(shodan_key, conflict) if shodan_key else {}
        wayback_result = await _fetch_wayback_snapshots(conflict)
        whois_dns = await _fetch_whois_dns(conflict)
        wigle_result = await _fetch_wigle_networks(conflict)
        techint_score = _compute_techint_score(
            tech_indicators, export_controls, ioda_events,
            ooni_result, cloudflare_outages, shodan_activity,
            whois_dns, wigle_result,
        )
        rule_summary = _build_summary(
            tech_indicators, export_controls, ioda_events, ioda_result,
            ooni_result, cloudflare_outages, shodan_activity,
            techint_score, wayback_result, whois_dns, wigle_result,
        )
        llm_summary = await _generate_haiku_summary_techint(
            conflict, tech_indicators, export_controls, ioda_events, ioda_result,
            ooni_result, cloudflare_outages, shodan_activity, techint_score,
        )
        summary = llm_summary if llm_summary else rule_summary
        return {
            "tech_indicators": tech_indicators,
            "export_controls": export_controls,
            "ioda_events": ioda_events,
            "ioda_outages": ioda_result.get("outages") or [],
            "ioda_signals_raw": ioda_result.get("signals_raw") or [],
            "ioda_alerts": ioda_result.get("alerts") or [],
            "ioda_entities": ioda_result.get("entities") or [],
            "ooni": ooni_result,
            "cloudflare_outages": cloudflare_outages,
            "shodan": shodan_activity,
            "wayback": wayback_result,
            "whois_dns": whois_dns,
            "wigle": wigle_result,
            "techint_score": round(techint_score, 1),
            "summary": summary,
        }

    try:
        return run_async(_run())
    except Exception as e:
        return {
            "tech_indicators": [],
            "export_controls": [{"error": str(e)}],
            "ioda_events": [],
            "ioda_outages": [],
            "ioda_signals_raw": [],
            "ioda_alerts": [],
            "ioda_entities": [],
            "ooni": {},
            "cloudflare_outages": [],
            "shodan": {},
            "wayback": {},
            "whois_dns": {},
            "wigle": {},
            "techint_score": 30.0,
            "summary": f"TECHINT error: {e}",
        }
