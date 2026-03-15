"""
DIPLO / Legal Agent – Sanctions (OFAC, EU), UN/ICJ feeds, diplomatic signals.
Fetches: OFAC SDN list (bulk CSV/XML), EU consolidated sanctions (open data),
UN Security Council / ICJ RSS or press releases. Rule-based score from new listings and resolutions. No LLM.
"""
import asyncio
import csv
import io
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from .health_registry import get_health_registry
from .utils import (
    AgentMetadata,
    SourceResult,
    run_async,
    utc_now_iso,
    compute_confidence_from_sources,
)

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
# UN press releases (RSS) – primary and fallback (press.un.org often 404; news.un.org more stable)
UN_PRESS_RSS = "https://press.un.org/en/rss/press.xml"
UN_NEWS_RSS = "https://news.un.org/feed/subscribe/en/news/all/rss.xml"
# ICJ press (RSS) – URL may change; check https://www.icj-cij.org/en/press-releases
ICJ_RSS = "https://www.icj-cij.org/rss/en-press-releases.xml"

CONFLICT_SANCTION_KEYWORDS: Dict[str, List[str]] = {
    "iran": ["iran", "irgc", "iranian", "tehran", "qods", "khamenei"],
    "us-iran": ["iran", "irgc", "iranian", "tehran"],
    "russia": ["russia", "russian", "ukraine", "donbas", "crimea", "putin"],
    "ukraine": ["ukraine", "russia", "donbas", "crimea"],
    "syria": ["syria", "syrian", "assad"],
    "north korea": ["dprk", "north korea", "kim jong"],
    "middle east": ["iran", "irgc", "syria", "syrian", "hezbollah", "lebanon", "yemen", "houthi", "iraq", "israel", "gaza", "ofac", "sanctions"],
    "naher osten": ["iran", "irgc", "syria", "syrian", "hezbollah", "lebanon", "yemen", "houthi", "iraq", "israel", "gaza", "ofac", "sanctions"],
    "hezbollah": ["hezbollah", "lebanon", "nasrallah", "ofac", "sanctions", "iran", "irgc", "qods"],
    "houthis": ["houthi", "houthis", "yemen", "ansar allah", "ofac", "sanctions", "iran", "red sea"],
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
        async with httpx.AsyncClient(timeout=15.0, headers=_HTTP_HEADERS) as client:
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
                    "summary": summary,
                })
        return entries
    except httpx.HTTPStatusError as e:
        logger.warning("DIPLO: %s RSS failed HTTP %s – %s", label, e.response.status_code, url[:60])
        return [{"title": f"{label} error", "error": f"HTTP {e.response.status_code}"}]
    except Exception as e:
        logger.warning("DIPLO: %s RSS fetch failed: %s – %s", label, e, url[:60])
        return [{"title": f"{label} error", "error": str(e)}]


async def _fetch_un_icj_news(conflict: str) -> List[Dict[str, Any]]:
    """Combine UN and ICJ RSS for conflict-relevant items. Optionally classify via Haiku. Tries UN fallback if primary 404."""
    un_entries = await _fetch_diplo_rss(UN_PRESS_RSS, "UN", conflict)
    # If UN primary returned only error (e.g. 404), try UN News feed
    if un_entries and len(un_entries) == 1 and un_entries[0].get("error"):
        un_entries = await _fetch_diplo_rss(UN_NEWS_RSS, "UN News", conflict)
    icj_entries = await _fetch_diplo_rss(ICJ_RSS, "ICJ", conflict)
    combined = (un_entries or [])[:10] + (icj_entries or [])[:10]
    items = [e for e in combined if isinstance(e, dict) and "error" not in e][:15]
    if not items and (un_entries or icj_entries):
        err_un = (un_entries or [{}])[0].get("error") if un_entries else None
        err_icj = (icj_entries or [{}])[0].get("error") if icj_entries else None
        logger.info(
            "DIPLO: UN/ICJ – no items after filter (UN: %s, ICJ: %s). Keywords for conflict '%s' may not match feed content.",
            err_un or "ok but 0 match", err_icj or "ok but 0 match", conflict,
        )
    items = _classify_un_icj_news(items)
    return items


def _classify_un_icj_news(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach diplo_category and diplo_confidence; drop irrelevant with high confidence."""
    if not items:
        return items
    try:
        from services.haiku_service import batch_classify_diplo
        from .utils import run_async
        texts = [
            ((e.get("title") or "") + " " + (e.get("summary") or "")).strip()[:1500]
            for e in items
        ]
        results = run_async(batch_classify_diplo(texts))
        if not results or all(r is None for r in results):
            return items
        out = []
        for e, res in zip(items, results):
            if res and isinstance(res, dict):
                e["diplo_category"] = res.get("category", "irrelevant")
                e["diplo_confidence"] = float(res.get("confidence", 0))
                if e["diplo_category"] == "irrelevant" and e["diplo_confidence"] >= 0.7:
                    continue
            out.append(e)
        return out if out else items
    except Exception as e:
        logger.debug("DIPLO Haiku classify skipped: %s", e)
        return items


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
    if any(
        n.get("diplo_category") == "new_sanction" and float(n.get("diplo_confidence") or 0) >= 0.6
        for n in valid_news
    ):
        base += 5
    return min(100.0, max(0.0, base))


async def _generate_haiku_summary_diplo(
    conflict: str,
    ofac: Dict[str, Any],
    eu: Dict[str, Any],
    news: List[Dict[str, Any]],
    score: float,
) -> Optional[str]:
    """Optional 2-3 sentence analyst summary via haiku_service.analyst_summary."""
    try:
        from services.haiku_service import analyst_summary
        compact = {
            "conflict": conflict,
            "diplo_score": score,
            "ofac_matches": ofac.get("total_matches"),
            "eu_mentions": eu.get("keyword_mentions"),
            "un_icj_news_count": len([n for n in news if n.get("title") and "error" not in n]),
            "news_categories": [n.get("diplo_category") for n in news if n.get("diplo_category")],
        }
        import json
        data = json.dumps(compact, indent=2)
        system = (
            "You are a sanctions and diplomatic analyst. Summarize the following DIPLO data "
            "in 2-3 sentences: OFAC SDN, EU sanctions, UN/ICJ news (and any categories like new_sanction, "
            "icj_ruling). Focus on escalation signals. Write in English."
        )
        out = await analyst_summary(system=system, data=data, max_tokens=256)
        return out.strip() if out else None
    except Exception:
        return None


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
        ofac, eu, news = await asyncio.gather(
            _fetch_ofac_sdn(conflict),
            _fetch_eu_sanctions(conflict),
            _fetch_un_icj_news(conflict),
        )
        diplo_score = _compute_diplo_score(ofac, eu, news)
        rule_summary = _build_summary(ofac, eu, news, diplo_score)
        llm_summary = await _generate_haiku_summary_diplo(conflict, ofac, eu, news, diplo_score)
        summary = llm_summary if llm_summary else rule_summary
        return {
            "diplo_score": round(diplo_score, 1),
            "ofac_sdn": ofac,
            "eu_sanctions": eu,
            "un_icj_news": news,
            "summary": summary,
        }

    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        out = run_async(_run())
        duration_ms = int((time.perf_counter() - start) * 1000)
        ofac_ok = isinstance(out.get("ofac_sdn"), dict) and not out.get("ofac_sdn", {}).get("error")
        eu_ok = isinstance(out.get("eu_sanctions"), dict) and not out.get("eu_sanctions", {}).get("error")
        news_list = out.get("un_icj_news") or []
        news_ok = bool(news_list) and not (isinstance(news_list, list) and news_list and isinstance(news_list[0], dict) and news_list[0].get("error"))
        source_results = [
            SourceResult(name="OFAC SDN", status="ok" if ofac_ok else "error", fetched_at=fetched_at, record_count=out.get("ofac_sdn", {}).get("total_matches", 0) if ofac_ok else 0),
            SourceResult(name="EU sanctions", status="ok" if eu_ok else "error", fetched_at=fetched_at),
            SourceResult(name="UN/ICJ", status="ok" if news_ok else "error", fetched_at=fetched_at, record_count=len(news_list) if isinstance(news_list, list) else 0),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "diplo", sr)
        confidence = compute_confidence_from_sources(source_results)
        ok_count = sum(1 for s in source_results if s.status == "ok")
        data_freshness = "live" if ok_count >= 2 else "recent" if ok_count >= 1 else "stale" if out.get("diplo_score", 0) > 0 else "unavailable"
        meta = AgentMetadata(agent="diplo", fetched_at=fetched_at, duration_ms=duration_ms, sources=source_results, confidence=confidence, data_freshness=data_freshness, fallback_used=False, error_summary=None)
        out["_meta"] = meta.model_dump(mode="json")
        return out
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        meta = AgentMetadata(agent="diplo", fetched_at=fetched_at, duration_ms=duration_ms, sources=[], confidence=compute_confidence_from_sources([]), data_freshness="unavailable", fallback_used=True, error_summary=str(e))
        return {
            "diplo_score": 28.0,
            "ofac_sdn": {"total_matches": 0, "sample": [], "error": str(e)},
            "eu_sanctions": {"keyword_mentions": 0, "error": str(e)},
            "un_icj_news": [],
            "summary": f"DIPLO error: {e}",
            "_meta": meta.model_dump(mode="json"),
        }
