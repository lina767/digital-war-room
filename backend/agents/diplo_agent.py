"""
DIPLO / Legal Agent – Sanctions (OFAC, EU), UN/ICJ feeds, diplomatic signals.
Fetches: OFAC SDN list (bulk CSV/XML), EU consolidated sanctions (open data),
UN Security Council / ICJ RSS or press releases, Treasury/OFAC recent actions.
Rule-based score from new listings and resolutions. No LLM.
"""
import asyncio
import csv
import io
import logging
import re
import time
from typing import Any, Dict, List

import httpx

from .utils import run_async

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": "DigitalWarRoom/1.0 (compliance-monitoring)",
    "Accept": "*/*",
}

# OFAC SDN list (bulk CSV – free, no key, headerless)
OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
# EU consolidated list – CSV version (much smaller than the XML)
EU_SANCTIONS_CSV_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
EU_SANCTIONS_XML_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xml/fullSanctionsList_1_1.xml"
# Treasury press releases (includes OFAC actions, advisories)
TREASURY_RSS_URL = "https://home.treasury.gov/system/files/126/ofac_rss.xml"
TREASURY_PRESS_RSS = "https://home.treasury.gov/rss/press-releases"
# UN press releases (RSS)
UN_PRESS_RSS = "https://press.un.org/en/rss/press.xml"
# ICJ press (RSS)
ICJ_RSS = "https://www.icj-cij.org/rss/en-press-releases.xml"

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


# ── Streaming HTTP helper ────────────────────────────────────────────────────

async def _stream_download(url: str, connect_s: float = 15, read_s: float = 90) -> str:
    """Stream-download a large file with separate connect/read timeouts."""
    timeout = httpx.Timeout(connect=connect_s, read=read_s, write=30.0, pool=15.0)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=_HTTP_HEADERS,
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[str] = []
            async for chunk in resp.aiter_text(chunk_size=65536):
                chunks.append(chunk)
            return "".join(chunks)


# ── OFAC SDN ─────────────────────────────────────────────────────────────────

_ofac_cache: Dict[str, Any] = {"text": None, "ts": 0.0}
_OFAC_CACHE_TTL = 6 * 3600


async def _fetch_ofac_sdn(conflict: str) -> Dict[str, Any]:
    """Fetch OFAC SDN list via streaming download.
    The SDN CSV is headerless with columns: ent_num, name, type, program, title, ...
    Caches raw text for 6h."""
    keywords = _conflict_to_keywords(conflict)
    try:
        now = time.time()
        if _ofac_cache["text"] and (now - _ofac_cache["ts"]) < _OFAC_CACHE_TTL:
            text = _ofac_cache["text"]
        else:
            logger.info("OFAC SDN: streaming download from %s", OFAC_SDN_CSV_URL)
            text = await _stream_download(OFAC_SDN_CSV_URL, connect_s=15, read_s=120)
            _ofac_cache["text"] = text
            _ofac_cache["ts"] = now
            logger.info("OFAC SDN: downloaded %d bytes", len(text))

        # SDN CSV columns (headerless): 0=ent_num, 1=name, 2=type, 3=program, 4=title, ...
        reader = csv.reader(io.StringIO(text))
        matches: List[Dict[str, Any]] = []
        programs_seen: Dict[str, int] = {}
        for row in reader:
            if len(row) < 4:
                continue
            name = (row[1] or "").strip().lower()
            program = (row[3] or "").strip().lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                prog_raw = (row[3] or "").strip()
                matches.append({
                    "name": row[1].strip(),
                    "type": row[2].strip() if len(row) > 2 else "",
                    "program": prog_raw,
                })
                for p in prog_raw.replace(";", " ").replace(",", " ").split():
                    p = p.strip(" '\"[]")
                    if p and len(p) > 1:
                        programs_seen[p] = programs_seen.get(p, 0) + 1
        top_programs = sorted(programs_seen.items(), key=lambda x: -x[1])[:10]
        return {
            "total_matches": len(matches),
            "sample": matches[:20],
            "programs": [{"name": p, "count": c} for p, c in top_programs],
            "error": None,
        }
    except Exception as e:
        logger.warning("OFAC SDN fetch failed: %s", e)
        return {"total_matches": 0, "sample": [], "programs": [], "error": str(e)}


# ── EU sanctions ─────────────────────────────────────────────────────────────

_eu_cache: Dict[str, Any] = {"text": None, "ts": 0.0}
_EU_CACHE_TTL = 6 * 3600


async def _fetch_eu_sanctions(conflict: str) -> Dict[str, Any]:
    """Fetch EU consolidated sanctions list. Tries CSV first (smaller), falls back to XML.
    Caches for 6h."""
    keywords = _conflict_to_keywords(conflict)
    try:
        now = time.time()
        if _eu_cache["text"] and (now - _eu_cache["ts"]) < _EU_CACHE_TTL:
            text = _eu_cache["text"]
        else:
            try:
                logger.info("EU sanctions: trying CSV endpoint")
                text = await _stream_download(EU_SANCTIONS_CSV_URL, connect_s=15, read_s=60)
            except Exception:
                logger.info("EU sanctions: CSV failed, falling back to XML")
                text = await _stream_download(EU_SANCTIONS_XML_URL, connect_s=15, read_s=90)
            _eu_cache["text"] = text
            _eu_cache["ts"] = now
            logger.info("EU sanctions: downloaded %d bytes", len(text))

        count = 0
        for k in keywords:
            count += len(re.findall(re.escape(k), text, re.I))
        return {"keyword_mentions": count, "error": None}
    except Exception as e:
        logger.warning("EU sanctions fetch failed: %s", e)
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


async def _fetch_ofac_recent_actions(conflict: str) -> List[Dict[str, Any]]:
    """Fetch OFAC/Treasury recent actions from RSS feeds.
    Tries the OFAC-specific RSS first, then the general Treasury press releases."""
    import feedparser
    keywords = _conflict_to_keywords(conflict)
    sanctions_keywords = ["sanction", "ofac", "sdn", "advisory", "designation",
                          "enforcement", "compliance", "embargo"]
    all_keywords = keywords + sanctions_keywords
    entries: List[Dict[str, Any]] = []

    for url, label in [(TREASURY_RSS_URL, "OFAC"), (TREASURY_PRESS_RSS, "Treasury")]:
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, headers=_HTTP_HEADERS,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
            for e in getattr(feed, "entries", [])[:30]:
                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or e.get("description") or "")[:600]
                combined_text = (title + " " + summary).lower()
                if any(k in combined_text for k in all_keywords):
                    entries.append({
                        "title": title,
                        "url": e.get("link"),
                        "published": e.get("published"),
                        "source": label,
                        "summary": summary[:300],
                    })
            if entries:
                break
        except Exception as e:
            logger.debug("OFAC recent actions fetch from %s failed: %s", url, e)
            continue

    return entries[:10]


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
    """Run DIPLO/Legal agent: OFAC SDN, EU sanctions, UN/ICJ RSS, OFAC recent actions."""
    async def _run() -> Dict[str, Any]:
        ofac, eu, news, recent_actions = await asyncio.gather(
            _fetch_ofac_sdn(conflict),
            _fetch_eu_sanctions(conflict),
            _fetch_un_icj_news(conflict),
            _fetch_ofac_recent_actions(conflict),
        )
        diplo_score = _compute_diplo_score(ofac, eu, news)
        summary = _build_summary(ofac, eu, news, diplo_score)
        return {
            "diplo_score": round(diplo_score, 1),
            "ofac_sdn": ofac,
            "eu_sanctions": eu,
            "un_icj_news": news,
            "ofac_recent_actions": recent_actions,
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
            "ofac_recent_actions": [],
            "summary": f"DIPLO error: {e}",
        }
