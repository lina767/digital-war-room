"""
CYBER / Threat Intel Agent – CISA KEV, threat reports, optional AlienVault OTX, optional GreyNoise scan context.
Fetches: CISA Known Exploited Vulnerabilities catalog, threat/APT RSS feeds,
optional OTX pulses, optional GreyNoise GNQL stats (malicious/recent scanners). No LLM; rule-based score.
"""
import asyncio
import os
from typing import Any, Dict, List

import httpx

CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# GreyNoise: scan context via GNQL stats (header: key). Optional GREYNOISE_API_KEY.
GREYNOISE_GNQL_STATS_URL = "https://api.greynoise.io/v2/experimental/gnql/stats"
# Threat intel RSS (vendor blogs, no API key)
THREAT_RSS = [
    "https://www.mandiant.com/resources/blog/rss.xml",
    "https://www.crowdstrike.com/blog/feed/",
]
OTX_PULSES_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"
OTX_INDICATORS_URL = "https://otx.alienvault.com/api/v1/indicators/export"

CONFLICT_COUNTRY_CODES: Dict[str, List[str]] = {
    "iran": ["IR"],
    "us-iran": ["IR", "US"],
    "russia": ["RU"],
    "ukraine": ["UA"],
    "china": ["CN"],
    "taiwan": ["TW"],
    "north korea": ["KP"],
}


def _conflict_to_keywords(conflict: str) -> List[str]:
    """Keywords for filtering threat reports / OTX."""
    cl = (conflict or "").lower()
    if "iran" in cl:
        return ["iran", "apt33", "apt34", "muddywater", "charming kitten", "oilrig"]
    if "russia" in cl or "ukraine" in cl:
        return ["russia", "ukraine", "sandworm", "apt28", "apt29", "gamaredon", "voodoobear"]
    if "china" in cl or "taiwan" in cl:
        return ["china", "apt40", "apt41", "mustang panda", "taiwan"]
    if "north korea" in cl:
        return ["north korea", "lazarus", "apt38"]
    return [cl] if cl else []


async def _fetch_cisa_kev() -> Dict[str, Any]:
    """Fetch CISA Known Exploited Vulnerabilities catalog (free, no key)."""
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(CISA_KEV_URL)
            resp.raise_for_status()
            data = resp.json()
        vulns = data.get("vulnerabilities") or []
        return {
            "total": len(vulns),
            "sample": vulns[:15],
            "error": None,
        }
    except Exception as e:
        return {"total": 0, "sample": [], "error": str(e)}


async def _fetch_threat_rss(conflict: str) -> List[Dict[str, Any]]:
    """Fetch threat intel RSS and filter by conflict keywords."""
    import feedparser
    keywords = _conflict_to_keywords(conflict)
    entries: List[Dict[str, Any]] = []
    for url in THREAT_RSS[:2]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
            for e in getattr(feed, "entries", [])[:10]:
                title = (e.get("title") or "").strip()
                link = e.get("link") or ""
                summary = (e.get("summary") or e.get("description") or "")[:300]
                if not keywords or any(k in (title + summary).lower() for k in keywords):
                    entries.append({"title": title, "url": link, "summary": summary[:200]})
        except Exception as e:
            entries.append({"title": "Feed error", "url": url, "error": str(e)})
    return entries[:20]


async def _fetch_otx_pulses(api_key: str, conflict: str) -> List[Dict[str, Any]]:
    """Fetch AlienVault OTX pulses (optional OTX_API_KEY). Filter by conflict."""
    if not api_key or not api_key.strip():
        return []
    keywords = _conflict_to_keywords(conflict)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                OTX_PULSES_URL,
                params={"limit": 30},
                headers={"X-OTX-API-KEY": api_key.strip()},
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        out = []
        for p in results:
            name = (p.get("name") or "").lower()
            desc = (p.get("description") or "").lower()
            if not keywords or any(k in name or k in desc for k in keywords):
                out.append({
                    "name": p.get("name"),
                    "id": p.get("id"),
                    "created": p.get("created"),
                    "author_name": (p.get("author_name") or ""),
                })
        return out[:15]
    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_greynoise_scan_context(api_key: str) -> Dict[str, Any]:
    """
    Fetch GreyNoise scan context: GNQL stats for recent malicious scanners.
    Query: malicious classification, last 7 days. Returns count + top actors/countries.
    Requires GREYNOISE_API_KEY (header: key). See https://docs.greynoise.io/reference/gnqlstats-1
    """
    if not api_key or not api_key.strip():
        return {"available": False, "error": "GREYNOISE_API_KEY not set"}
    # GNQL: malicious scanners seen in last week (last_seen:1w = last 7 days, UTC)
    query = "classification:malicious last_seen:1w"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                GREYNOISE_GNQL_STATS_URL,
                params={"query": query, "count": 10},
                headers={"key": api_key.strip(), "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return {"available": False, "error": f"GreyNoise API {resp.status_code}", "count": 0}
            data = resp.json()
        count = int(data.get("count") or 0)
        stats = data.get("stats") or {}
        actors = [x for x in (stats.get("actors") or [])[:5] if isinstance(x, dict) and x.get("actor")]
        source_countries = [x for x in (stats.get("source_countries") or [])[:5] if isinstance(x, dict) and x.get("actor")]
        classifications = [x for x in (stats.get("classifications") or []) if isinstance(x, dict)]
        return {
            "available": True,
            "count": count,
            "query": query,
            "top_actors": [{"actor": a.get("actor"), "count": a.get("count")} for a in actors],
            "top_source_countries": [{"country": c.get("actor"), "count": c.get("count")} for c in source_countries],
            "classifications": [{"classification": c.get("classification"), "count": c.get("count")} for c in classifications],
            "error": None,
        }
    except Exception as e:
        return {"available": False, "error": str(e), "count": 0}


def _compute_cyber_score(kev: Dict, threat_reports: List[Dict], otx_pulses: List[Dict], greynoise: Dict) -> float:
    """Compute CYBER escalation score 0–100 from KEV, threat reports, OTX, and GreyNoise scan context."""
    base = 25.0
    total_kev = int(kev.get("total") or 0)
    if total_kev > 400:
        base += 20
    elif total_kev > 200:
        base += 12
    elif total_kev > 100:
        base += 8
    valid_reports = [r for r in threat_reports if "error" not in (r or {}) and r.get("title") and "Feed error" not in (r.get("title") or "")]
    if len(valid_reports) >= 5:
        base += 25
    elif len(valid_reports) >= 2:
        base += 15
    elif len(valid_reports) >= 1:
        base += 8
    valid_otx = [p for p in otx_pulses if "error" not in (p or {}) and p.get("name")]
    if len(valid_otx) >= 3:
        base += 22
    elif len(valid_otx) >= 1:
        base += 10
    # GreyNoise scan context: malicious scanners in last 7d
    if greynoise.get("available") and int(greynoise.get("count") or 0) > 0:
        base += min(8, 2 + (int(greynoise.get("count") or 0) // 5000))
    return min(100.0, max(0.0, base))


def _build_summary(kev: Dict, threat_reports: List[Dict], otx_pulses: List[Dict], greynoise: Dict, score: float) -> str:
    parts = []
    if kev.get("total"):
        parts.append(f"CISA KEV: {kev['total']} known exploited vulnerabilities.")
    valid_r = [r for r in threat_reports if r.get("title") and "error" not in r]
    if valid_r:
        parts.append(f"Threat reports: {len(valid_r)} conflict-related items.")
    valid_o = [p for p in otx_pulses if p.get("name") and "error" not in p]
    if valid_o:
        parts.append(f"OTX pulses: {len(valid_o)} relevant.")
    if greynoise.get("available") and greynoise.get("count") is not None:
        parts.append(f"GreyNoise: {greynoise['count']} malicious scanners (7d); top actors/countries in context.")
    elif greynoise.get("error") and "not set" not in str(greynoise.get("error", "")):
        parts.append("GreyNoise: scan context unavailable.")
    if not parts:
        return "CYBER: No CISA KEV, threat RSS, OTX, or GreyNoise data available."
    return "CYBER: " + " ".join(parts)


def run_cyber_agent(conflict: str) -> Dict[str, Any]:
    """Run CYBER/Threat Intel agent: CISA KEV, threat RSS, optional OTX, optional GreyNoise scan context."""
    otx_key = os.getenv("OTX_API_KEY")
    greynoise_key = os.getenv("GREYNOISE_API_KEY")

    async def _run() -> Dict[str, Any]:
        kev = await _fetch_cisa_kev()
        threat_reports = await _fetch_threat_rss(conflict)
        otx_pulses = await _fetch_otx_pulses(otx_key or "", conflict) if otx_key else []
        greynoise = await _fetch_greynoise_scan_context(greynoise_key or "") if greynoise_key else {"available": False, "error": "GREYNOISE_API_KEY not set", "count": 0}
        cyber_score = _compute_cyber_score(kev, threat_reports, otx_pulses, greynoise)
        summary = _build_summary(kev, threat_reports, otx_pulses, greynoise, cyber_score)
        return {
            "cyber_score": round(cyber_score, 1),
            "cisa_kev": kev,
            "threat_reports": threat_reports,
            "otx_pulses": otx_pulses,
            "greynoise_scan_context": greynoise,
            "summary": summary,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        return {
            "cyber_score": 25.0,
            "cisa_kev": {"total": 0, "sample": [], "error": str(e)},
            "threat_reports": [],
            "otx_pulses": [],
            "greynoise_scan_context": {"available": False, "error": str(e), "count": 0},
            "summary": f"CYBER error: {e}",
        }
