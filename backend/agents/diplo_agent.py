"""
DIPLO / Legal Agent – Sanctions (OFAC, EU), UN/ICJ feeds, diplomatic signals.
Fetches: OFAC SDN list (bulk CSV/XML), EU consolidated sanctions (open data),
UN Security Council / ICJ RSS or press releases. Rule-based score from new listings and resolutions.
No LLM.
"""
import asyncio
import csv
import io
import os
import re
from typing import Any, Dict, List

import httpx

from .utils import run_async

# OFAC SDN list (bulk CSV – free, no key)
OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
# EU consolidated list (open data) – XML or CSV
EU_SANCTIONS_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xml/fullSanctionsList_1_1.xml"
# UN press releases (RSS)
UN_PRESS_RSS = "https://press.un.org/en/rss/press.xml"
# ICJ press (RSS)
ICJ_RSS = "https://www.icj-cij.org/rss/en-press-releases.xml"

# Country/entity keywords per conflict for filtering OFAC/EU
CONFLICT_SANCTION_KEYWORDS: Dict[str, List[str]] = {
    "iran": ["iran", "irgc", "iranian", "tehran", "qods", "khamenei"],
    "us-iran": ["iran", "irgc", "iranian", "tehran"],
    "russia": ["russia", "russian", "ukraine", "donbas", "crimea", "putin"],
    "ukraine": ["ukraine", "russia", "donbas", "crimea"],
    "syria": ["syria", "syrian", "assad"],
    "north korea": ["dprk", "north korea", "kim jong"],
    "default": ["iran", "russia", "syria"],
}


def _conflict_to_keywords(conflict: str) -> List[str]:
    cl = (conflict or "").lower()
    for k, v in CONFLICT_SANCTION_KEYWORDS.items():
        if k != "default" and k in cl:
            return v
    return CONFLICT_SANCTION_KEYWORDS["default"]


async def _fetch_ofac_sdn(conflict: str) -> Dict[str, Any]:
    """Fetch OFAC SDN list and count/filter by conflict-relevant entities (CSV bulk)."""
    keywords = _conflict_to_keywords(conflict)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(OFAC_SDN_CSV_URL)
            resp.raise_for_status()
            text = resp.text
        reader = csv.DictReader(io.StringIO(text))
        matches: List[Dict[str, Any]] = []
        for row in reader:
            if not row:
                continue
            # SDN CSV: name, type, program, title, etc.
            name = (row.get("name") or row.get("firstName", "") + " " + row.get("lastName", "")).lower()
            program = (row.get("programs") or row.get("program", "") or "").lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                matches.append({
                    "name": row.get("name") or (row.get("firstName", "") + " " + row.get("lastName", "")).strip(),
                    "type": row.get("type"),
                    "program": row.get("programs") or row.get("program"),
                })
        return {"total_matches": len(matches), "sample": matches[:20], "error": None}
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e)}


async def _fetch_eu_sanctions(conflict: str) -> Dict[str, Any]:
    """Fetch EU consolidated list (XML) and count conflict-relevant entries."""
    keywords = _conflict_to_keywords(conflict)
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(EU_SANCTIONS_URL)
            resp.raise_for_status()
            text = resp.text
        # Simple tag-based count; full parsing would use xml.etree
        count = 0
        for k in keywords:
            count += len(re.findall(re.escape(k), text, re.I))
        return {"keyword_mentions": count, "error": None}
    except Exception as e:
        return {"keyword_mentions": 0, "error": str(e)}


async def _fetch_diplo_rss(url: str, label: str, conflict: str) -> List[Dict[str, Any]]:
    """Fetch UN or ICJ RSS and filter by conflict keywords."""
    import feedparser
    keywords = _conflict_to_keywords(conflict)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        entries = []
        for e in getattr(feed, "entries", [])[:20]:
            title = (e.get("title") or "").strip()
            summary = (e.get("summary") or e.get("description") or "")[:400]
            if not keywords or any(k in (title + summary).lower() for k in keywords):
                entries.append({
                    "title": title,
                    "url": e.get("link"),
                    "published": e.get("published"),
                    "source": label,
                })
        return entries
    except Exception as e:
        return [{"title": f"{label} error", "error": str(e)}]


async def _fetch_un_icj_news(conflict: str) -> List[Dict[str, Any]]:
    """Combine UN and ICJ RSS for conflict-relevant items."""
    un_entries = await _fetch_diplo_rss(UN_PRESS_RSS, "UN", conflict)
    icj_entries = await _fetch_diplo_rss(ICJ_RSS, "ICJ", conflict)
    combined = (un_entries or [])[:10] + (icj_entries or [])[:10]
    return [e for e in combined if isinstance(e, dict) and "error" not in e][:15]


def _compute_diplo_score(ofac: Dict[str, Any], eu: Dict[str, Any], news: List[Dict[str, Any]]) -> float:
    """Score 0–100: more sanctions matches and UN/ICJ coverage = higher diplomatic tension."""
    base = 28.0
    ofac_count = int(ofac.get("total_matches") or 0)
    if ofac_count > 500:
        base += 22
    elif ofac_count > 200:
        base += 15
    elif ofac_count > 50:
        base += 10
    elif ofac_count > 0:
        base += 5
    eu_mentions = int(eu.get("keyword_mentions") or 0)
    if eu_mentions > 1000:
        base += 15
    elif eu_mentions > 100:
        base += 8
    valid_news = [n for n in news if n.get("title") and "error" not in n]
    if len(valid_news) >= 5:
        base += 20
    elif len(valid_news) >= 2:
        base += 10
    elif len(valid_news) >= 1:
        base += 5
    return min(100.0, max(0.0, base))


def _build_summary(ofac: Dict[str, Any], eu: Dict[str, Any], news: List[Dict[str, Any]], score: float) -> str:
    parts = []
    if ofac.get("total_matches"):
        parts.append(f"OFAC SDN: {ofac['total_matches']} conflict-relevant entries.")
    if ofac.get("error"):
        parts.append("OFAC: fetch failed.")
    if eu.get("keyword_mentions", 0) > 0:
        parts.append(f"EU sanctions: {eu['keyword_mentions']} keyword mentions.")
    valid_n = [n for n in news if n.get("title") and "error" not in n]
    if valid_n:
        parts.append(f"UN/ICJ: {len(valid_n)} relevant press items.")
    if not parts:
        return "DIPLO: No OFAC, EU sanctions, or UN/ICJ data available."
    return "DIPLO: " + " ".join(parts)


def run_diplo_agent(conflict: str) -> Dict[str, Any]:
    """Run DIPLO/Legal agent: OFAC SDN, EU sanctions, UN/ICJ RSS."""
    async def _run() -> Dict[str, Any]:
        ofac = await _fetch_ofac_sdn(conflict)
        eu = await _fetch_eu_sanctions(conflict)
        news = await _fetch_un_icj_news(conflict)
        diplo_score = _compute_diplo_score(ofac, eu, news)
        summary = _build_summary(ofac, eu, news, diplo_score)
        return {
            "diplo_score": round(diplo_score, 1),
            "ofac_sdn": ofac,
            "eu_sanctions": eu,
            "un_icj_news": news,
            "summary": summary,
        }

    try:
        return run_async(_run())
    except Exception as e:
        return {
            "diplo_score": 28.0,
            "ofac_sdn": {"total_matches": 0, "sample": [], "error": str(e)},
            "eu_sanctions": {"keyword_mentions": 0, "error": str(e)},
            "un_icj_news": [],
            "summary": f"DIPLO error: {e}",
        }
